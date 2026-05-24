"""Integration tests: eBay sold price staging → price_observation.

Closes GitHub issue #64 — [Feature]: Save results to DB.

test_staged_row_is_promoted_to_price_observation:
    Deterministic. Seeds one row in ebay_scraped_sold, calls promote_sold_obs
    with real asyncpg repos, asserts the row lands in price_observation.
    No network. Runs in CI.

test_live_sheoldred_pipeline:
    Live smoke test. Calls the real eBay Finding API for Sheoldred DMU,
    inserts valid sold items, promotes them, and prints a human-readable
    price summary. Requires EBAY_APP_ID env var. Excluded from CI.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration]

_YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)


async def test_staged_row_is_promoted_to_price_observation(db_pool, seeded_db):
    """One staged USD/FOIL/NM row must appear in price_observation after promote_sold_obs."""
    from automana.core.repositories.app_integration.ebay.sales_repository import (
        EbaySalesRepository,
    )
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
        EbayScrapeSoldRepository,
    )
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
    from automana.core.services.app_integration.ebay.promote_sold_obs_service import (
        promote_sold_obs,
    )

    source_product_id = seeded_db["source_product_id"]
    language_id = seeded_db["language_id"]

    # Step 1: insert staging row
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pricing.ebay_scraped_sold "
            "(item_id, title, source_product_id, price_cents, currency, marketplace_id, "
            " condition_id, finish_id, language_id, sold_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            "TEST-ITEM-001",
            "Sheoldred the Apocalypse DMU Foil NM MTG",
            source_product_id,
            1250,          # $12.50 USD
            "USD",
            "EBAY-US",
            1,             # condition_id=1 → NM
            2,             # finish_id=2 → FOIL
            language_id,
            _YESTERDAY,
        )

    # Step 2: run promote_sold_obs with real repos
    async with db_pool.acquire() as conn:
        result = await promote_sold_obs(
            ebay_sales_repository=EbaySalesRepository(conn),
            ebay_scrape_repository=EbayScrapeSoldRepository(conn),
            fx_rates_repository=FxRatesRepository(conn),
        )

    assert result["promoted"] == 1, (
        f"Expected 1 row promoted, got {result['promoted']}. "
        "Check that GET_UNPROMOTED_SCRAPED filters by promoted_to_obs=false and source_product_id IS NOT NULL."
    )

    # Step 3: verify price_observation
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sold_avg_cents, sold_count FROM pricing.price_observation "
            "WHERE source_product_id = $1",
            source_product_id,
        )

    assert row is not None, (
        f"No row found in price_observation for source_product_id={source_product_id}. "
        "Check that upsert_price_observation writes to pricing.price_observation."
    )
    assert row["sold_avg_cents"] == 1250, (
        f"Expected sold_avg_cents=1250, got {row['sold_avg_cents']}. "
        "Check _aggregate in promote_sold_obs_service.py."
    )
    assert row["sold_count"] == 1, (
        f"Expected sold_count=1, got {row['sold_count']}. "
        "Multiple rows aggregated — check GET_UNPROMOTED_SCRAPED scope."
    )

    # Verify the staging row was actually marked promoted (not just any row being counted)
    async with db_pool.acquire() as conn:
        flag = await conn.fetchval(
            "SELECT promoted_to_obs FROM pricing.ebay_scraped_sold "
            "WHERE item_id = 'TEST-ITEM-001'",
        )
    assert flag is True, (
        "Staging row item_id='TEST-ITEM-001' was not marked promoted_to_obs=true. "
        "Check mark_promoted in EbayScrapeSoldRepository."
    )


@pytest.mark.live
@pytest.mark.skipif(
    not os.getenv("EBAY_APP_ID"),
    reason="EBAY_APP_ID not set — live eBay API test skipped",
)
async def test_live_sheoldred_pipeline(db_pool, seeded_db):
    """Live smoke: fetch real Sheoldred DMU sold prices from eBay, promote to price_observation.

    Run with:
        EBAY_APP_ID=<your-app-id> pytest tests/integration/services/ebay/ -m "integration and live" -s
    """
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )
    from automana.core.repositories.app_integration.ebay.sales_repository import (
        EbaySalesRepository,
    )
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
        EbayScrapeSoldRepository,
    )
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
    from automana.core.services.app_integration.ebay.promote_sold_obs_service import (
        promote_sold_obs,
    )
    from automana.core.services.app_integration.ebay.title_parser import (
        FINISH_ID_MAP,
        CONDITION_ID_MAP,
        parse_finish_code,
        parse_condition_code,
        parse_frame_variant,
        conflicts_with_expected,
    )
    from automana.core.services.app_integration.ebay.market_price_scorer import score_title

    _SHEOLDRED = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "DMU",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }

    source_product_id = seeded_db["source_product_id"]
    language_id = seeded_db["language_id"]
    app_id = os.environ["EBAY_APP_ID"]

    # Fetch real eBay sold listings — no mock
    finding = EbayFindingAPIRepository(environment="production")
    items = await finding.find_completed_items(
        "Sheoldred the Apocalypse DMU",
        app_id,
        global_id="EBAY-US",
        limit=10,
    )

    inserted = 0
    async with db_pool.acquire() as conn:
        ebay_scrape = EbayScrapeSoldRepository(conn)

        for item in items:
            if score_title(
                item["title"],
                _SHEOLDRED["card_name"],
                _SHEOLDRED["set_code"],
                is_foil=None,
                frame=None,
            ) < 0.7:
                continue
            if conflicts_with_expected(parse_frame_variant(item["title"]), _SHEOLDRED):
                continue

            if not item.get("sold_date"):
                continue
            if not item.get("item_id"):
                continue

            finish_code = parse_finish_code(item["title"])
            condition_code = parse_condition_code(item.get("condition"), item["title"])

            await ebay_scrape.insert_scraped_sold(
                item_id=item["item_id"],
                title=item["title"],
                source_product_id=source_product_id,
                price_cents=int(float(item["price"]) * 100),
                currency=item.get("currency", "USD"),
                marketplace_id="EBAY-US",
                condition_id=CONDITION_ID_MAP.get(condition_code, 1),
                finish_id=FINISH_ID_MAP.get(finish_code, 1),
                language_id=language_id,
                sold_at=datetime.fromisoformat(
                    item["sold_date"].replace("Z", "+00:00")
                ),
            )
            inserted += 1

        result = await promote_sold_obs(
            ebay_sales_repository=EbaySalesRepository(conn),
            ebay_scrape_repository=ebay_scrape,
            fx_rates_repository=FxRatesRepository(conn),
        )

    # Human-readable summary — visible with -s flag
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT sold_avg_cents, sold_count FROM pricing.price_observation "
            "WHERE source_product_id = $1",
            source_product_id,
        )

    print(
        f"\n[live] eBay items fetched={len(items)}  "
        f"inserted={inserted}  promoted={result['promoted']}"
    )
    for r in rows:
        avg_usd = r["sold_avg_cents"] / 100
        print(f"  price_observation: avg=${avg_usd:.2f}  count={r['sold_count']}")

    assert len(items) > 0, (
        "eBay returned 0 results for 'Sheoldred the Apocalypse DMU' — "
        "check EBAY_APP_ID is valid and the Finding API is reachable."
    )
    assert inserted > 0, (
        f"0 items passed the scorer (eBay returned {len(items)} raw results). "
        "Check score_title threshold or that titles contain the card name and set code."
    )
    assert result["promoted"] >= 1, (
        "No rows were promoted to price_observation. "
        "Check promote_sold_obs_service._promote_channel."
    )
    assert all(r["sold_avg_cents"] > 0 for r in rows), (
        "price_observation row has sold_avg_cents=0 — check _aggregate price calculation."
    )
