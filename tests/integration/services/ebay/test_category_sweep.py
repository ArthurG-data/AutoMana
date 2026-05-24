"""Integration tests for the eBay category sweep pipeline.

test_category_sweep_ingest:
    Seeds 2 matchable eBay source_products + writes a synthetic sweep JSON.
    Runs EbayCategorySweepService in replay mode (no network).
    Asserts: 2 rows in ebay_scraped_sold, noise item skipped.

test_watchlist_pagination_ingest:
    Seeds 1 source_product + writes a 150-item synthetic watchlist JSON.
    Runs scrape_global_market_service._scrape_one_card in replay mode.
    Asserts: 150 rows inserted, no duplicate item_ids.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration]

_YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)


# ── helpers ────────────────────────────────────────────────────────────────

def _make_sweep_item(item_id: str, title: str, price: float = 10.0) -> dict:
    return {
        "item_id": item_id,
        "title": title,
        "price": price,
        "currency": "USD",
        "condition": "Used",
        "url": None,
        "sold_date": _YESTERDAY.isoformat(),
    }


def _write_sweep_json(base_dir: Path, marketplace: str, items: list[dict]) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = base_dir / today / "sweep" / f"{marketplace}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "marketplace": marketplace,
        "source_product_id": None,
        "items": items,
    }
    path.write_text(json.dumps(payload))
    return path


def _write_watchlist_json(base_dir: Path, spid: int, marketplace: str, items: list[dict]) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = base_dir / today / "watchlist" / f"{spid}_{marketplace}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "marketplace": marketplace,
        "source_product_id": spid,
        "items": items,
    }
    path.write_text(json.dumps(payload))
    return path


# ── fixtures ───────────────────────────────────────────────────────────────

async def _seed_extra_source_product(conn, seeded_db: dict) -> int:
    """Seed a second eBay card (Atraxa ONE) sharing the same FK spine."""
    set_type_id = await conn.fetchval(
        "INSERT INTO card_catalog.set_type_list_ref (set_type) VALUES ('expansion') "
        "ON CONFLICT (set_type) DO UPDATE SET set_type = EXCLUDED.set_type RETURNING set_type_id"
    )
    rarity_id = await conn.fetchval(
        "INSERT INTO card_catalog.rarities_ref (rarity_name) VALUES ('mythic') "
        "ON CONFLICT (rarity_name) DO UPDATE SET rarity_name = EXCLUDED.rarity_name RETURNING rarity_id"
    )
    border_id = await conn.fetchval(
        "INSERT INTO card_catalog.border_color_ref (border_color_name) VALUES ('black') "
        "ON CONFLICT (border_color_name) DO UPDATE SET border_color_name = EXCLUDED.border_color_name RETURNING border_color_id"
    )
    frame_id = await conn.fetchval(
        "INSERT INTO card_catalog.frames_ref (frame_year) VALUES ('2015') "
        "ON CONFLICT (frame_year) DO UPDATE SET frame_year = EXCLUDED.frame_year RETURNING frame_id"
    )
    layout_id = await conn.fetchval(
        "INSERT INTO card_catalog.layouts_ref (layout_name) VALUES ('normal') "
        "ON CONFLICT (layout_name) DO UPDATE SET layout_name = EXCLUDED.layout_name RETURNING layout_id"
    )
    unique_card_id = await conn.fetchval(
        "INSERT INTO card_catalog.unique_cards_ref (card_name) VALUES ($1) RETURNING unique_card_id",
        f"Atraxa, Praetors' Voice [{uuid.uuid4().hex[:6].upper()}]",
    )
    set_code = "ONE" + uuid.uuid4().hex[:4].upper()
    set_id = await conn.fetchval(
        "INSERT INTO card_catalog.sets (set_name, set_code, set_type_id, released_at) "
        "VALUES ($1, $2, $3, '2023-02-10') RETURNING set_id",
        f"Phyrexia All Will Be One [{set_code}]", set_code, set_type_id,
    )
    card_version_id = await conn.fetchval(
        "INSERT INTO card_catalog.card_version "
        "(unique_card_id, set_id, collector_number, rarity_id, border_color_id, frame_id, layout_id) "
        "VALUES ($1, $2, '10', $3, $4, $5, $6) RETURNING card_version_id",
        unique_card_id, set_id, rarity_id, border_id, frame_id, layout_id,
    )
    game_id = await conn.fetchval("SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'")
    product_id = await conn.fetchval(
        "INSERT INTO pricing.product_ref (game_id) VALUES ($1) RETURNING product_id", game_id
    )
    await conn.execute(
        "INSERT INTO pricing.mtg_card_products (product_id, card_version_id) VALUES ($1, $2)",
        product_id, card_version_id,
    )
    ebay_source_id = await conn.fetchval("SELECT source_id FROM pricing.price_source WHERE code = 'ebay'")
    source_product_id = await conn.fetchval(
        "INSERT INTO pricing.source_product (product_id, source_id) VALUES ($1, $2) "
        "ON CONFLICT (product_id, source_id) DO UPDATE SET product_id = EXCLUDED.product_id "
        "RETURNING source_product_id",
        product_id, ebay_source_id,
    )
    return source_product_id


# ── tests ──────────────────────────────────────────────────────────────────

async def test_category_sweep_ingest(db_pool, seeded_db, tmp_path):
    """Replay mode: 2 matching items inserted, 1 noise item skipped."""
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import EbayScrapeSoldRepository
    from automana.core.services.app_integration.ebay.category_sweep_service import ebay_category_sweep

    spid_1 = seeded_db["source_product_id"]

    async with db_pool.acquire() as conn:
        spid_2 = await _seed_extra_source_product(conn, seeded_db)

    # Build sweep JSON: 2 matching + 1 noise
    card_name_1 = seeded_db["card_name"]  # e.g. "Sheoldred, the Apocalypse [ABCDEF]"
    sweep_items = [
        _make_sweep_item("SWEEP-001", f"{card_name_1} NM MTG", price=18.99),
        _make_sweep_item("SWEEP-002", "Atraxa Praetors Voice ONE NM MTG", price=9.50),
        _make_sweep_item("SWEEP-003", "MTG lot 200 random bulk commons", price=5.00),
    ]
    _write_sweep_json(tmp_path, "EBAY-US", sweep_items)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.aclose = AsyncMock()

    import automana.core.services.app_integration.ebay.category_sweep_service as svc_mod

    with patch.object(svc_mod, "get_settings") as mock_settings, \
         patch("automana.core.services.app_integration.ebay.ebay_raw_io.get_ebay_raw_dir", return_value=tmp_path), \
         patch("automana.core.services.app_integration.ebay.category_sweep_service.aioredis") as mock_aioredis:
        mock_settings.return_value = MagicMock(ebay_app_id="test-app-id", redis_host="localhost", redis_port=6379)
        mock_aioredis.from_url.return_value = mock_redis

        with patch.object(svc_mod, "_MARKETPLACES", ("EBAY-US",)):
            async with db_pool.acquire() as conn:
                result = await ebay_category_sweep(
                    ebay_sales_repository=EbaySalesRepository(conn),
                    ebay_scrape_repository=EbayScrapeSoldRepository(conn),
                    ebay_finding_repository=AsyncMock(),
                )

    assert result["fetched"] == 3
    assert result["matched"] == 2, f"Expected 2 matched, got {result['matched']}"
    assert result["inserted"] == 2, f"Expected 2 inserted, got {result['inserted']}"

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM pricing.ebay_scraped_sold WHERE item_id = ANY($1::text[])",
            ["SWEEP-001", "SWEEP-002"],
        )
    assert count == 2, f"Expected 2 rows in ebay_scraped_sold, found {count}"

    # Cleanup extra seeded card (seeded_db fixture handles the first)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE item_id = ANY($1::text[])",
            ["SWEEP-001", "SWEEP-002", "SWEEP-003"],
        )
        await conn.execute("DELETE FROM pricing.source_product WHERE source_product_id = $1", spid_2)


async def test_watchlist_pagination_ingest(db_pool, seeded_db, tmp_path):
    """Replay mode: 150-item watchlist JSON fully inserted with no duplicate item_ids."""
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import EbayScrapeSoldRepository
    from automana.core.services.app_integration.ebay.scrape_global_market_service import _scrape_one_card

    spid = seeded_db["source_product_id"]
    card_name = seeded_db["card_name"]

    watchlist_items = [
        {
            "item_id": f"WATCH-{i:04d}",
            "title": f"{card_name} NM MTG",
            "price": 18.99,
            "currency": "USD",
            "condition": "Used",
            "url": None,
            "sold_date": _YESTERDAY.isoformat(),
        }
        for i in range(150)
    ]
    _write_watchlist_json(tmp_path, spid, "EBAY-US", watchlist_items)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.aclose = AsyncMock()

    card = {
        "card_name": card_name,
        "set_code": "DMU",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }

    with patch("automana.core.services.app_integration.ebay.ebay_raw_io.get_ebay_raw_dir", return_value=tmp_path):
        async with db_pool.acquire() as conn:
            ebay_scrape = EbayScrapeSoldRepository(conn)
            count = await _scrape_one_card(
                card_version_id=seeded_db["card_version_id"],
                card=card,
                app_id="test-app-id",
                marketplace="EBAY-US",
                min_date=_YESTERDAY - timedelta(days=1),
                limit_per_card=100,
                score_threshold=0.5,
                ebay_sales_repository=AsyncMock(),
                ebay_scrape_repository=ebay_scrape,
                ebay_finding_repository=AsyncMock(),
                source_product_id=spid,
                today=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                redis_client=mock_redis,
            )

    assert count == 150, f"Expected 150 rows inserted, got {count}"

    async with db_pool.acquire() as conn:
        ids_in_db = await conn.fetch(
            "SELECT item_id FROM pricing.ebay_scraped_sold WHERE source_product_id = $1", spid
        )
    assert len(ids_in_db) == 150
    assert len({r["item_id"] for r in ids_in_db}) == 150, "Duplicate item_ids detected"

    # Cleanup (seeded_db fixture also runs DELETE on source_product_id after yield)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE source_product_id = $1", spid
        )


@pytest.mark.live
@pytest.mark.skipif(
    not os.getenv("EBAY_APP_ID"),
    reason="EBAY_APP_ID not set — live eBay API test skipped",
)
async def test_live_category_sweep(db_pool, seeded_db, tmp_path):
    """Live smoke: real eBay category API call, at least 1 item matched and staged.

    Run with:
        EBAY_APP_ID=<your-app-id> pytest tests/integration/services/ebay/ -m "integration and live" -s
    """
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import EbayScrapeSoldRepository
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import EbayFindingAPIRepository
    from automana.core.services.app_integration.ebay.category_sweep_service import ebay_category_sweep
    import automana.core.services.app_integration.ebay.category_sweep_service as svc_mod

    app_id = os.environ["EBAY_APP_ID"]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch.object(svc_mod, "get_settings") as mock_settings, \
         patch("automana.core.services.app_integration.ebay.ebay_raw_io.get_ebay_raw_dir", return_value=tmp_path), \
         patch("automana.core.services.app_integration.ebay.category_sweep_service.aioredis") as mock_aioredis, \
         patch.object(svc_mod, "_SWEEP_MAX_PAGES", 1):
        mock_settings.return_value = MagicMock(ebay_app_id=app_id, redis_host="localhost", redis_port=6379)
        mock_aioredis.from_url.return_value = mock_redis
        with patch.object(svc_mod, "_MARKETPLACES", ("EBAY-US",)):
            async with db_pool.acquire() as conn:
                result = await ebay_category_sweep(
                    ebay_sales_repository=EbaySalesRepository(conn),
                    ebay_scrape_repository=EbayScrapeSoldRepository(conn),
                    ebay_finding_repository=EbayFindingAPIRepository(environment="production"),
                )

    print(f"\n[live] fetched={result['fetched']}  matched={result['matched']}  inserted={result['inserted']}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sweep_file = tmp_path / today / "sweep" / "EBAY-US.json"
    assert sweep_file.exists(), "Sweep JSON file was not written to disk"

    assert result["fetched"] > 0, "eBay returned 0 items — check EBAY_APP_ID validity"
    assert result["matched"] >= 1, (
        f"0 items matched from {result['fetched']} fetched — "
        "check score threshold and that eBay-sourced cards exist in the DB"
    )

    # Cleanup
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE source_product_id = $1",
            seeded_db["source_product_id"],
        )
