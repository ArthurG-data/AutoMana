# eBay Sold Price Integration Test — Design Spec

**Date:** 2026-05-24
**Status:** Approved
**Closes:** GitHub issue #64 — [Feature]: Save results to DB

---

## Goal

Prove, via integration tests against a real TimescaleDB container, that eBay sold price
data flows correctly from `pricing.ebay_scraped_sold` into `pricing.price_observation`
through the `promote_sold_obs` service.

Issue #64 asked for persistent Browse API outputs. Scope has been redirected to the
Finding API sold-price pipeline (already implemented), which is the more valuable data
source for MTG finance analytics. The tests close the issue by verifying the persistence
guarantee that was the acceptance criterion.

---

## Scope

- New directory: `tests/integration/services/ebay/`
- Two tests in `test_promote_sold_obs.py`:
  1. **Deterministic** — seeds synthetic data, no network, runs in CI
  2. **Live smoke test** — calls the real eBay Finding API, skipped in CI

No changes to service or repository code. No new migrations.

---

## Architecture

```
[conftest.py]  seeded_db fixture
                └─► seeds Sheoldred card (real name, set_code=DMU)
                └─► seeds product_ref → mtg_card_products → source_product (eBay)
                └─► cleans up in FK teardown order

[test 1 — deterministic]
    seed ebay_scraped_sold (item_id=TEST-ITEM-001, USD, FOIL, NM, 1250 cents)
    │
    ▼
    promote_sold_obs(real repos against test DB)
    │
    ▼
    assert price_observation: count=1, sold_avg_cents=1250, sold_count=1

[test 2 — live, @pytest.mark.live]
    EbayFindingAPIRepository(production)
    find_completed_items("Sheoldred the Apocalypse DMU", limit=10)
    │
    ▼
    score + parse each result (scorer + title_parser)
    insert valid results into ebay_scraped_sold (seeded source_product_id)
    │
    ▼
    promote_sold_obs(real repos)
    │
    ▼
    assert price_observation: at least 1 row with sold_avg_cents > 0
    print human-readable summary (count, min/max USD cents)
```

---

## New Files

```
tests/integration/services/ebay/
    __init__.py
    conftest.py               ← db_pool + seeded_db fixture
    test_promote_sold_obs.py  ← test_staged_row_promoted + test_live_sheoldred_pipeline
```

---

## conftest.py

Inherits `timescale_container`, `_test_env`, `db_migrations_applied` from the parent
`tests/integration/conftest.py` (same fixture chain as the mtgjson tests).

`db_pool` fixture: scoped to `function`, creates an asyncpg pool pointed at the test
container (identical shape to `tests/integration/services/mtgjson/conftest.py`).

`seeded_db` fixture: seeds and tears down in FK order.

**Seed sequence:**

```python
# Reference rows (upsert so they survive repeated runs)
set_type_id  = upsert("card_catalog.set_type_list_ref",  set_type="expansion")
rarity_id    = upsert("card_catalog.rarities_ref",       rarity_name="mythic")
border_id    = upsert("card_catalog.border_color_ref",   border_color_name="black")
frame_id     = upsert("card_catalog.frames_ref",         frame_year="2015")
layout_id    = upsert("card_catalog.layouts_ref",        layout_name="normal")

# Unique set — fresh per invocation to avoid inter-test conflicts
set_code = "DMU"   # real set code makes output readable
set_id   = INSERT INTO card_catalog.sets (set_name="Dominaria United",
                                          set_code=set_code, ...)

# Card
unique_card_id = INSERT INTO card_catalog.unique_cards_ref
                    (card_name="Sheoldred, the Apocalypse")
card_version_id = INSERT INTO card_catalog.card_version (...)

# Pricing chain
game_id    = SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'
product_id = INSERT INTO pricing.product_ref (game_id)
             INSERT INTO pricing.mtg_card_products (product_id, card_version_id)

# eBay source — looked up dynamically, never hardcoded
ebay_source_id = SELECT source_id FROM pricing.price_source WHERE code = 'ebay'
source_product_id = INSERT INTO pricing.source_product (product_id, source_id=ebay_source_id)
                    ON CONFLICT DO UPDATE RETURNING source_product_id
```

**Teardown** (reverse FK order):
`price_observation` → `source_product` → `mtg_card_products` → `product_ref`
→ `card_version` → `unique_cards_ref` → `sets`
Also deletes any `ebay_scraped_sold` rows for the seeded `source_product_id`.

---

## Test 1 — Deterministic (CI-safe)

**`test_staged_row_is_promoted_to_price_observation`**

```python
# Insert staging row
await conn.execute(
    "INSERT INTO pricing.ebay_scraped_sold "
    "(item_id, title, source_product_id, price_cents, currency, marketplace_id, "
    " finish_id, condition_id, language_id, sold_at) "
    "VALUES ('TEST-ITEM-001', 'Sheoldred the Apocalypse DMU Foil NM', $1, "
    "        1250, 'USD', 'EBAY-US', 2, 1, 1, $2)",
    source_product_id, yesterday_utc,
)

# Wire real repos against a single connection
async with db_pool.acquire() as conn:
    ebay_sales  = EbaySalesRepository(conn)
    ebay_scrape = EbayScrapeSoldRepository(conn)
    fx_rates    = FxRatesRepository(conn)
    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

assert result["promoted"] == 1

row = await conn.fetchrow(
    "SELECT sold_avg_cents, sold_count FROM pricing.price_observation "
    "WHERE source_product_id = $1",
    source_product_id,
)
assert row["sold_avg_cents"] == 1250
assert row["sold_count"] == 1
```

---

## Test 2 — Live Smoke Test

**`test_live_sheoldred_pipeline`**

Markers: `@pytest.mark.live` and `@pytest.mark.skipif(not os.getenv("EBAY_APP_ID"), ...)`.

```python
from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
)
from automana.core.services.app_integration.ebay.title_parser import (
    parse_finish, parse_condition, parse_frame_variant, conflicts_with_expected,
)
from automana.core.services.app_integration.ebay.market_price_scorer import score_title

SHEOLDRED = {
    "card_name": "Sheoldred, the Apocalypse",
    "set_code": "DMU",
    "frame_effects": [],
    "is_promo": False,
    "promo_types": [],
    "border_color_name": "black",
    "full_art": False,
}

app_id  = os.environ["EBAY_APP_ID"]
finding = EbayFindingAPIRepository(environment="production")
items   = await finding.find_completed_items(
    "Sheoldred the Apocalypse DMU",
    app_id,
    global_id="EBAY-US",
    limit=10,
)

inserted = 0
async with db_pool.acquire() as conn:
    ebay_scrape = EbayScrapeSoldRepository(conn)
    for item in items:
        if score_title(item["title"], SHEOLDRED["card_name"], SHEOLDRED["set_code"]) < 0.7:
            continue
        parsed_frame = parse_frame_variant(item["title"])
        if conflicts_with_expected(parsed_frame, SHEOLDRED):
            continue
        await ebay_scrape.insert_scraped_sold(
            item_id=item["item_id"],
            title=item["title"],
            source_product_id=source_product_id,
            price_cents=int(float(item["price"]) * 100),
            currency=item.get("currency", "USD"),
            marketplace_id="EBAY-US",
            condition_id=parse_condition(item.get("condition"), item["title"]),
            finish_id=parse_finish(item["title"]),
            language_id=1,
            sold_at=datetime.fromisoformat(item["sold_date"].replace("Z", "+00:00")),
        )
        inserted += 1

    ebay_sales = EbaySalesRepository(conn)
    fx_rates   = FxRatesRepository(conn)
    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

# Human-readable summary
rows = await conn.fetch(
    "SELECT sold_avg_cents, sold_count FROM pricing.price_observation "
    "WHERE source_product_id = $1",
    source_product_id,
)
print(f"\n[live] eBay items fetched: {len(items)}, inserted: {inserted}, promoted: {result['promoted']}")
for r in rows:
    print(f"  price_observation: avg={r['sold_avg_cents']}¢  count={r['sold_count']}")

assert result["promoted"] >= 1, "Expected at least one row promoted from real eBay data"
assert all(r["sold_avg_cents"] > 0 for r in rows)
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| eBay API returns 0 results for Sheoldred | Test fails with clear message; indicates scorer or keywords are too strict |
| All items fail scorer in live test | `inserted == 0`; assert `promoted >= 1` fails — investigate title patterns |
| FX rates table empty | `promote_sold_obs` degrades to face value (existing behaviour); test unaffected |
| Teardown fails partway | Each DELETE is independent; orphan rows are cleaned on next fixture run via ON CONFLICT DO UPDATE |

---

## pytest.ini / pyproject.toml

Add marker declaration so `pytest.mark.live` doesn't produce a warning:

```ini
[pytest]
markers =
    live: marks tests that require real external API access (deselect with -m "not live")
```

---

## Out of Scope

- Testing `scrape_global_market` end-to-end against a real DB (unit tests already cover it)
- Multi-card promotion batching (unit tests for `_aggregate` cover this)
- FX conversion integration (unit tests in `test_promote_sold_obs_service.py` already cover it)
- Any service or repository code changes
