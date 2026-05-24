# eBay Sold Price Integration Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove via integration tests against a real TimescaleDB container that eBay sold price data flows from `pricing.ebay_scraped_sold` into `pricing.price_observation` through `promote_sold_obs`; closes GitHub issue #64.

**Architecture:** Two tests in `tests/integration/services/ebay/test_promote_sold_obs.py`: one deterministic (seeds staging, calls real repos, asserts) and one `@pytest.mark.live` smoke test that calls the real eBay Finding API for Sheoldred and verifies real market prices survive the full pipeline. Follows the existing `tests/integration/services/mtgjson/` pattern exactly.

**Tech Stack:** Python 3.12, asyncpg, asyncio, pytest-asyncio, testcontainers (TimescaleDB), eBay Finding API (live test only)

**Spec:** `docs/superpowers/specs/2026-05-24-ebay-sold-price-integration-test-design.md`

---

## File Map

**Create:**
- `tests/integration/services/ebay/__init__.py`
- `tests/integration/services/ebay/conftest.py` — `db_pool` + `seeded_db` fixture
- `tests/integration/services/ebay/test_promote_sold_obs.py` — both tests

**Modify:**
- `pytest.ini` — add `live` marker declaration

---

## Task 1: Directory scaffold and conftest.py

**Files:**
- Create: `tests/integration/services/ebay/__init__.py`
- Create: `tests/integration/services/ebay/conftest.py`

- [ ] **Step 1: Create the `__init__.py`**

```bash
touch tests/integration/services/ebay/__init__.py
```

- [ ] **Step 2: Write `conftest.py`**

```python
# tests/integration/services/ebay/conftest.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg
import pytest_asyncio


@pytest_asyncio.fixture(scope="function")
async def db_pool(timescale_container, _test_env, db_migrations_applied):
    host = timescale_container.get_container_host_ip()
    port = timescale_container.get_exposed_port(5432)
    pool = await asyncpg.create_pool(
        host=host,
        port=int(port),
        user="automana_test",
        password="test_password",
        database="automana_test",
        min_size=1,
        max_size=3,
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def seeded_db(db_pool):
    """Seed Sheoldred through the full FK chain and clean up after."""
    async with db_pool.acquire() as conn:
        # --- Reference rows (upsert — safe on repeated runs) ---
        set_type_id = await conn.fetchval(
            "INSERT INTO card_catalog.set_type_list_ref (set_type) VALUES ('expansion') "
            "ON CONFLICT (set_type) DO UPDATE SET set_type = EXCLUDED.set_type "
            "RETURNING set_type_id"
        )
        rarity_id = await conn.fetchval(
            "INSERT INTO card_catalog.rarities_ref (rarity_name) VALUES ('mythic') "
            "ON CONFLICT (rarity_name) DO UPDATE SET rarity_name = EXCLUDED.rarity_name "
            "RETURNING rarity_id"
        )
        border_id = await conn.fetchval(
            "INSERT INTO card_catalog.border_color_ref (border_color_name) VALUES ('black') "
            "ON CONFLICT (border_color_name) DO UPDATE SET border_color_name = EXCLUDED.border_color_name "
            "RETURNING border_color_id"
        )
        frame_id = await conn.fetchval(
            "INSERT INTO card_catalog.frames_ref (frame_year) VALUES ('2015') "
            "ON CONFLICT (frame_year) DO UPDATE SET frame_year = EXCLUDED.frame_year "
            "RETURNING frame_id"
        )
        layout_id = await conn.fetchval(
            "INSERT INTO card_catalog.layouts_ref (layout_name) VALUES ('normal') "
            "ON CONFLICT (layout_name) DO UPDATE SET layout_name = EXCLUDED.layout_name "
            "RETURNING layout_id"
        )

        # --- Unique card name per run (avoids UNIQUE conflict if fixture runs twice) ---
        card_name = f"Sheoldred, the Apocalypse [{uuid.uuid4().hex[:6].upper()}]"
        unique_card_id = await conn.fetchval(
            "INSERT INTO card_catalog.unique_cards_ref (card_name) VALUES ($1) "
            "RETURNING unique_card_id",
            card_name,
        )

        # --- Unique set per run ---
        set_code = "DMU" + uuid.uuid4().hex[:4].upper()
        set_id = await conn.fetchval(
            "INSERT INTO card_catalog.sets (set_name, set_code, set_type_id, released_at) "
            "VALUES ($1, $2, $3, '2022-09-09') RETURNING set_id",
            f"Dominaria United [{set_code}]", set_code, set_type_id,
        )

        card_version_id = await conn.fetchval(
            "INSERT INTO card_catalog.card_version "
            "(unique_card_id, set_id, collector_number, rarity_id, border_color_id, frame_id, layout_id) "
            "VALUES ($1, $2, '328', $3, $4, $5, $6) RETURNING card_version_id",
            unique_card_id, set_id, rarity_id, border_id, frame_id, layout_id,
        )

        # --- Pricing chain ---
        game_id = await conn.fetchval(
            "SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'"
        )
        product_id = await conn.fetchval(
            "INSERT INTO pricing.product_ref (game_id) VALUES ($1) RETURNING product_id",
            game_id,
        )
        await conn.execute(
            "INSERT INTO pricing.mtg_card_products (product_id, card_version_id) VALUES ($1, $2)",
            product_id, card_version_id,
        )

        # --- eBay source — looked up dynamically, never hardcoded ---
        ebay_source_id = await conn.fetchval(
            "SELECT source_id FROM pricing.price_source WHERE code = 'ebay'"
        )
        source_product_id = await conn.fetchval(
            "INSERT INTO pricing.source_product (product_id, source_id) VALUES ($1, $2) "
            "ON CONFLICT (product_id, source_id) DO UPDATE SET source_id = EXCLUDED.source_id "
            "RETURNING source_product_id",
            product_id, ebay_source_id,
        )

        # --- English language_id ---
        language_id = await conn.fetchval(
            "SELECT language_id FROM card_catalog.language_ref WHERE language_code = 'en'"
        )

    yield {
        "card_name": card_name,
        "card_version_id": card_version_id,
        "product_id": product_id,
        "source_product_id": source_product_id,
        "language_id": language_id,
        "unique_card_id": unique_card_id,
        "set_id": set_id,
    }

    # --- Teardown: remove committed rows in reverse FK order ---
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE source_product_id = $1",
            source_product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.price_observation WHERE source_product_id = $1",
            source_product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.source_product WHERE source_product_id = $1",
            source_product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.mtg_card_products WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.product_ref WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM card_catalog.card_version WHERE card_version_id = $1",
            card_version_id,
        )
        await conn.execute(
            "DELETE FROM card_catalog.unique_cards_ref WHERE unique_card_id = $1",
            unique_card_id,
        )
        await conn.execute(
            "DELETE FROM card_catalog.sets WHERE set_id = $1", set_id
        )
```

- [ ] **Step 3: Verify the fixture tree resolves**

```bash
pytest tests/integration/services/ebay/ --collect-only -m integration 2>&1 | head -20
```

Expected: no import errors, no fixture resolution errors. (No tests collected yet is fine.)

---

## Task 2: Deterministic integration test

**Files:**
- Create: `tests/integration/services/ebay/test_promote_sold_obs.py`

- [ ] **Step 1: Write the test file with the deterministic test**

```python
# tests/integration/services/ebay/test_promote_sold_obs.py
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
    assert row["sold_count"] == 1
```

- [ ] **Step 2: Run the deterministic test**

```bash
pytest tests/integration/services/ebay/test_promote_sold_obs.py::test_staged_row_is_promoted_to_price_observation -v -m integration -s
```

Expected output:
```
PASSED tests/integration/services/ebay/test_promote_sold_obs.py::test_staged_row_is_promoted_to_price_observation
```

If it fails, the most likely causes:
- `seeded_db` fixture can't find `card_catalog.card_games_ref WHERE code = 'mtg'` → check that migrations ran
- `price_observation` has extra PK columns not matched by the upsert → check `pricing.price_observation` schema in `06_prices.sql`
- `promote_sold_obs` returns `promoted=0` → check that `GET_UNPROMOTED_SCRAPED` in `ebay_scrape_queries.py` filters on `promoted_to_obs = false`

- [ ] **Step 3: Commit the passing test**

```bash
git add tests/integration/services/ebay/__init__.py \
        tests/integration/services/ebay/conftest.py \
        tests/integration/services/ebay/test_promote_sold_obs.py
git commit -m "test(integration): eBay sold price staging→price_observation deterministic test"
```

---

## Task 3: Add `live` marker and write the live smoke test

**Files:**
- Modify: `pytest.ini`
- Modify: `tests/integration/services/ebay/test_promote_sold_obs.py`

- [ ] **Step 1: Add `live` marker to `pytest.ini`**

Open `pytest.ini` and add one line under `markers =`:

```ini
    live: tests requiring real external API access (skip with -m "not live")
```

The full markers block should look like:
```ini
markers =
    unit: Unit tests (no DB, no HTTP, no Redis)
    integration: Integration tests (real DB, real Redis, mocked HTTP boundary)
    api: Router + service + repository full-stack tests
    repository: Repository-layer tests (DB only, no router)
    service: Service tests
    pipeline: Celery pipeline chain tests
    ebay: eBay integration tests (real Redis required)
    slow: Tests expected to run >10s (excluded from default run via -m "not slow")
    live: tests requiring real external API access (skip with -m "not live")
```

- [ ] **Step 2: Append the live smoke test to `test_promote_sold_obs.py`**

Add this function at the end of the file:

```python
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

    assert inserted > 0, (
        f"0 items passed the scorer for 'Sheoldred the Apocalypse DMU'. "
        f"eBay returned {len(items)} raw results. Check score_title threshold or keyword."
    )
    assert result["promoted"] >= 1, (
        "No rows were promoted to price_observation. "
        "Check promote_sold_obs_service._promote_channel."
    )
    assert all(r["sold_avg_cents"] > 0 for r in rows), (
        "price_observation row has sold_avg_cents=0 — check _aggregate price calculation."
    )
```

- [ ] **Step 3: Verify live test is skipped in normal runs**

```bash
pytest tests/integration/services/ebay/ -m "integration and not live" -v
```

Expected: only `test_staged_row_is_promoted_to_price_observation` runs; live test is skipped or deselected.

- [ ] **Step 4: Run the live test with your eBay App ID**

```bash
EBAY_APP_ID=<your-app-id> pytest tests/integration/services/ebay/test_promote_sold_obs.py::test_live_sheoldred_pipeline \
    -m "integration and live" -v -s
```

Expected output includes a summary line like:
```
[live] eBay items fetched=10  inserted=6  promoted=6
  price_observation: avg=$14.23  count=6
PASSED
```

If `inserted=0`: the scorer rejected all titles. Run with `-s` to see what eBay returned and inspect `score_title` for the first item manually.

If `promoted=0` but `inserted>0`: `GET_UNPROMOTED_SCRAPED` is not picking up the rows — verify `promoted_to_obs` column defaults to `false` in the schema.

- [ ] **Step 5: Commit**

```bash
git add pytest.ini \
        tests/integration/services/ebay/test_promote_sold_obs.py
git commit -m "test(integration): add live Sheoldred smoke test + live pytest marker"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| New dir `tests/integration/services/ebay/` | Task 1 |
| `conftest.py` with `db_pool` + `seeded_db` | Task 1 |
| FK chain: card_version → product_ref → mtg_card_products → source_product | Task 1 |
| eBay `source_id` looked up dynamically (never hardcoded) | Task 1 |
| Deterministic test — seed staging, run service, assert | Task 2 |
| `sold_avg_cents=1250`, `sold_count=1` assertions | Task 2 |
| `live` marker in `pytest.ini` | Task 3 |
| `@pytest.mark.live` + `skipif` on `EBAY_APP_ID` | Task 3 |
| Real `EbayFindingAPIRepository(environment="production")` | Task 3 |
| Score + parse each item before insert | Task 3 |
| Human-readable summary printed with `-s` | Task 3 |
| `assert inserted > 0` + `assert promoted >= 1` | Task 3 |
| Teardown in FK order | Task 1 |

**Placeholder scan:** None found — all steps contain exact code.

**Type consistency:**
- `parse_finish_code` / `parse_condition_code` — Task 3 matches Task 1's `title_parser` imports (`FINISH_ID_MAP`, `CONDITION_ID_MAP` also imported and used consistently)
- `source_product_id` — yielded as int from `seeded_db`, passed as int throughout
- `language_id` — fetched dynamically from DB, passed to `insert_scraped_sold` as int
- `score_title` — called with all 5 args (`title, card_name, set_code, is_foil=None, frame=None`) matching the actual signature
