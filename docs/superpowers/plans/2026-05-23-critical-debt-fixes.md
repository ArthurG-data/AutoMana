# Critical Debt Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two live data-correctness issues: drain 5.8M MTGStock reject rows blocked by unapplied migration, and wire FX conversion into `promote_sold_obs` so AUD/CAD eBay prices are stored in USD.

**Architecture:**
- C1 is operational only — verify migration_40 is applied, call `pricing.resolve_price_rejects()` via the CLI, measure new link rate.
- C3 adds a `get_rates_for_date` read method to `FxRatesRepository`, updates `GET_UNPROMOTED_SCRAPED` to include the `currency` column, and threads an `fx_map` dict through `_aggregate → _promote_channel → promote_sold_obs`. The scrape channel applies the map; the own-sales channel passes `None` (USD only).

**Tech Stack:** Python 3.12, asyncpg, FastAPI ServiceRegistry pattern, pytest-asyncio, `automana-run` CLI for operational steps.

---

## Task 1: Verify migration_40 and drain MTGStock rejects (C1/P1)

**No code changes required — this is a verification + operational trigger.**

**Files:**
- No changes — operational only

- [ ] **Step 1: Verify migration_40 seed tables are populated**

Run inside the dev DB container:

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT
  (SELECT count(*) FROM pricing.mtgstock_art_set_map)   AS art_map_rows,
  (SELECT count(*) FROM pricing.mtgstock_token_set_map) AS token_map_rows;
"
```

Expected output:
```
 art_map_rows | token_map_rows
--------------+----------------
           43 |            186
```

If either count is 0, migration_40 has not been applied. Apply it:

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
  < src/automana/database/SQL/migrations/migration_40_mtgstock_link_fixes.sql
```

Then re-run the verification query to confirm counts.

- [ ] **Step 2: Baseline — count existing unresolved rejects**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT
  COUNT(*)                                         AS total_rejects,
  COUNT(*) FILTER (WHERE resolved_at IS NULL
                     AND is_terminal IS FALSE)     AS unresolved,
  COUNT(*) FILTER (WHERE is_terminal = TRUE)       AS terminal
FROM pricing.stg_price_observation_reject;
"
```

Record the numbers — compare after the drain to measure improvement.

- [ ] **Step 3: Run `retry_rejects` via the CLI**

```bash
source .venv/bin/activate
automana-run mtg_stock.data_staging.retry_rejects \
  --ingestion-run-id 0 \
  2>&1 | tail -20
```

Expected output includes `"rows_resolved": <N>` where N > 0. This calls `pricing.resolve_price_rejects(p_limit := 50000, p_only_unresolved := true)` and re-feeds resolved rows into `stg_price_observation`.

The default `p_limit` is 50,000 per call. With ~5.8M rejects, run it repeatedly until it reports 0:

```bash
while true; do
  result=$(automana-run mtg_stock.data_staging.retry_rejects --ingestion-run-id 0 2>&1)
  echo "$result"
  resolved=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('rows_resolved',0))" 2>/dev/null || echo 0)
  [ "$resolved" -eq 0 ] && break
done
```

If `automana-run` does not accept `--ingestion-run-id`, call the service without it:

```bash
automana-run mtg_stock.data_staging.retry_rejects 2>&1 | tail -20
```

- [ ] **Step 4: Measure new link rate**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT
  COUNT(*)                                        AS total_rejects,
  COUNT(*) FILTER (WHERE resolved_at IS NULL
                    AND is_terminal IS FALSE)     AS still_unresolved,
  COUNT(*) FILTER (WHERE is_terminal = TRUE)      AS terminal,
  ROUND(100.0 * COUNT(*) FILTER (WHERE is_terminal = TRUE)
        / NULLIF(COUNT(*), 0), 2)                AS terminal_pct
FROM pricing.stg_price_observation_reject;
"
```

Target: `still_unresolved` drops from ~5.8M to < 10K (foil-suffix and no-set-abbr rows remain permanently unresolved).

- [ ] **Step 5: Commit a note to the backlog**

Update `docs/MASTER_TECHNICAL_DEBT.md` — mark C1/P1 as resolved with the measured terminal percentage.

```bash
git add docs/MASTER_TECHNICAL_DEBT.md
git commit -m "ops: drain MTGStock reject rows after migration_40 — measured <N>% terminal"
```

---

## Task 2: Add `get_rates_for_date` to `FxRatesRepository` (C3 — Part 1 of 3)

**Files:**
- Modify: `src/automana/core/repositories/pricing/fx_rates_repository.py`
- Test: `tests/unit/core/repositories/pricing/test_fx_rates_repository.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/repositories/pricing/test_fx_rates_repository.py`:

```python
import pytest
from unittest.mock import AsyncMock
from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
from datetime import date


@pytest.fixture
def repo():
    conn = AsyncMock()
    return FxRatesRepository(conn)


@pytest.mark.asyncio
async def test_get_rates_for_date_returns_rows(repo):
    repo.execute_query = AsyncMock(return_value=[
        {"from_currency": "AUD", "rate": 0.645},
        {"from_currency": "CAD", "rate": 0.731},
    ])
    rows = await repo.get_rates_for_date(date(2026, 5, 23))
    repo.execute_query.assert_called_once()
    args = repo.execute_query.call_args[0]
    assert "$1" in args[0]  # parameterised query
    assert args[1] == (date(2026, 5, 23),)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_get_rates_for_date_empty_when_no_rates(repo):
    repo.execute_query = AsyncMock(return_value=[])
    rows = await repo.get_rates_for_date(date(2026, 5, 23))
    assert rows == []
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/unit/core/repositories/pricing/test_fx_rates_repository.py -v
```

Expected: `AttributeError: 'FxRatesRepository' object has no attribute 'get_rates_for_date'`

- [ ] **Step 3: Implement `get_rates_for_date`**

Edit `src/automana/core/repositories/pricing/fx_rates_repository.py`:

```python
_GET_RATES_FOR_DATE = """
SELECT from_currency, rate
FROM pricing.fx_rates
WHERE to_currency = 'USD'
  AND rate_date = $1
ORDER BY from_currency;
"""


class FxRatesRepository(AbstractRepository):
    # ... existing methods unchanged ...

    async def get_rates_for_date(self, rate_date: date) -> list[dict]:
        rows = await self.execute_query(_GET_RATES_FOR_DATE, (rate_date,))
        return [dict(r) for r in rows] if rows else []
```

Add `_GET_RATES_FOR_DATE` after `_UPSERT_RATE` at module level. Add `get_rates_for_date` as the last method in the class.

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/unit/core/repositories/pricing/test_fx_rates_repository.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/pricing/fx_rates_repository.py \
        tests/unit/core/repositories/pricing/test_fx_rates_repository.py
git commit -m "feat(pricing): add FxRatesRepository.get_rates_for_date for FX lookup"
```

---

## Task 3: FX conversion in `_aggregate` and `_promote_channel` (C3 — Part 2 of 3)

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py`
- Modify: `src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py`
- Modify: `tests/unit/core/services/ebay/test_promote_sold_obs_service.py`

- [ ] **Step 1: Update `GET_UNPROMOTED_SCRAPED` to include `currency`**

In `ebay_scrape_queries.py`, replace:

```python
GET_UNPROMOTED_SCRAPED = """
SELECT scrape_id, source_product_id, price_cents, sold_at,
       finish_id, condition_id, language_id
FROM pricing.ebay_scraped_sold
WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;
"""
```

with:

```python
GET_UNPROMOTED_SCRAPED = """
SELECT scrape_id, source_product_id, price_cents, currency, sold_at,
       finish_id, condition_id, language_id
FROM pricing.ebay_scraped_sold
WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;
"""
```

- [ ] **Step 2: Write failing tests for FX conversion in `_aggregate`**

In `tests/unit/core/services/ebay/test_promote_sold_obs_service.py`, add these tests after the existing ones:

```python
# ── FX conversion ─────────────────────────────────────────────────────────────

def _aud_scrape_row(scrape_id, price_cents):
    return {
        "scrape_id": scrape_id,
        "source_product_id": SOURCE_ID,
        "price_cents": price_cents,
        "currency": "AUD",
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }


def test_aggregate_converts_aud_to_usd():
    """AUD 200 cents × 0.65 rate = 130 USD cents."""
    fx_map = {"AUD": 0.65, "CAD": 0.73}
    rows = [_aud_scrape_row(1, 200)]
    groups = _aggregate(rows, fx_map=fx_map)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 130


def test_aggregate_no_conversion_for_usd_rows():
    """USD rows must not be multiplied."""
    fx_map = {"AUD": 0.65}
    rows = [_scrape_row(1, 200)]  # existing helper — no currency field (→ USD default)
    groups = _aggregate(rows, fx_map=fx_map)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 200


def test_aggregate_unknown_currency_uses_face_value():
    """If fx_map has no entry for the currency, use face value and don't crash."""
    fx_map = {"AUD": 0.65}
    row = {
        "scrape_id": 1,
        "source_product_id": SOURCE_ID,
        "price_cents": 500,
        "currency": "GBP",  # not in fx_map
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }
    groups = _aggregate([row], fx_map=fx_map)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 500


def test_aggregate_no_fx_map_uses_face_value():
    """Passing fx_map=None must be identical to current behaviour."""
    rows = [_aud_scrape_row(1, 200)]
    groups = _aggregate(rows, fx_map=None)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 200
```

- [ ] **Step 3: Run to confirm they fail**

```bash
pytest tests/unit/core/services/ebay/test_promote_sold_obs_service.py -v -k "fx or aud or convert"
```

Expected: `TypeError: _aggregate() got an unexpected keyword argument 'fx_map'`

- [ ] **Step 4: Update `_aggregate` to apply FX conversion**

In `promote_sold_obs_service.py`, replace the `_aggregate` function:

```python
def _aggregate(rows: list[dict], fx_map: dict[str, float] | None = None) -> dict[tuple, dict]:
    """Group rows into (source_product_id, ts_date, finish_id, condition_id, language_id) buckets.

    fx_map maps currency codes → USD rate (e.g. {"AUD": 0.645, "CAD": 0.731}).
    Rows with currency absent or 'USD' are not converted.
    Rows with an unknown currency are passed through at face value.
    """
    groups: dict[tuple, dict] = defaultdict(lambda: {"total": 0, "count": 0, "ids": []})
    for row in rows:
        ts_date = row.get("sold_at")
        if hasattr(ts_date, "date"):
            ts_date = ts_date.date()
        elif not isinstance(ts_date, date):
            continue
        key = (
            row.get("source_product_id"),
            ts_date,
            row.get("finish_id", 1),
            row.get("condition_id") or 1,
            row.get("language_id", 1),
        )
        raw_cents = row.get("sold_price_cents") or row.get("price_cents") or 0
        currency = (row.get("currency") or "USD").upper()
        if fx_map and currency != "USD" and currency in fx_map:
            price_cents = round(raw_cents * fx_map[currency])
        else:
            price_cents = raw_cents
        bucket = groups[key]
        bucket["total"] += price_cents
        bucket["count"] += 1
        id_key = "ebay_osp_id" if "ebay_osp_id" in row else "scrape_id"
        bucket["ids"].append(row[id_key])
    return groups
```

- [ ] **Step 5: Update `_promote_channel` to accept and pass `fx_map`**

Replace the `_promote_channel` function signature and its `_aggregate` call:

```python
async def _promote_channel(staging_rows, mark_fn, upsert_fn, fx_map: dict[str, float] | None = None) -> int:
    if not staging_rows:
        return 0

    groups = _aggregate(staging_rows, fx_map=fx_map)
    # ... rest of the function unchanged ...
```

Only the first two lines change — the rest of the function body stays identical.

- [ ] **Step 6: Run the new tests to confirm they pass**

```bash
pytest tests/unit/core/services/ebay/test_promote_sold_obs_service.py -v
```

Expected: all tests PASS (new + existing).

- [ ] **Step 7: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py \
        src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py \
        tests/unit/core/services/ebay/test_promote_sold_obs_service.py
git commit -m "feat(ebay): apply FX conversion in _aggregate — AUD/CAD prices normalised to USD"
```

---

## Task 4: Wire FX rates into `promote_sold_obs` (C3 — Part 3 of 3)

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py`
- Modify: `tests/unit/core/services/ebay/test_promote_sold_obs_service.py`

- [ ] **Step 1: Write the failing test for FX wiring in `promote_sold_obs`**

Add to `tests/unit/core/services/ebay/test_promote_sold_obs_service.py`:

```python
# ── FX wiring in promote_sold_obs ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_promote_sold_obs_applies_fx_to_scrape_channel():
    """AUD 200-cent scrape row should land as 130 USD cents (0.65 rate)."""
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[])
    ebay_sales.mark_promoted = AsyncMock()
    ebay_sales.upsert_price_observation = AsyncMock()

    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[_aud_scrape_row(10, 200)])
    ebay_scrape.mark_promoted = AsyncMock()

    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[
        {"from_currency": "AUD", "rate": 0.65},
    ])

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

    assert result["promoted"] == 1
    upsert_call = ebay_sales.upsert_price_observation.call_args.kwargs
    assert upsert_call["sold_avg_cents"] == 130  # 200 * 0.65 = 130


@pytest.mark.asyncio
async def test_promote_sold_obs_skips_fx_when_no_rates_available():
    """If FX table has no rates today, promote at face value (no crash)."""
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[])
    ebay_sales.mark_promoted = AsyncMock()
    ebay_sales.upsert_price_observation = AsyncMock()

    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[_aud_scrape_row(10, 200)])
    ebay_scrape.mark_promoted = AsyncMock()

    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[])  # empty — network failure

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

    assert result["promoted"] == 1
    upsert_call = ebay_sales.upsert_price_observation.call_args.kwargs
    assert upsert_call["sold_avg_cents"] == 200  # face value fallback
```

- [ ] **Step 2: Run to confirm the tests fail**

```bash
pytest tests/unit/core/services/ebay/test_promote_sold_obs_service.py -v -k "fx_wiring or applies_fx or skips_fx"
```

Expected: `TypeError: promote_sold_obs() got an unexpected keyword argument 'fx_rates_repository'`

- [ ] **Step 3: Update `promote_sold_obs` to accept `fx_rates_repository` and apply FX**

In `promote_sold_obs_service.py`, make these changes:

**Add import at the top of the file:**

```python
from datetime import date

from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
```

**Update the `@ServiceRegistry.register` decorator:**

```python
@ServiceRegistry.register(
    path="integrations.ebay.promote_sold_obs",
    db_repositories=["ebay_sales", "ebay_scrape", "fx_rates"],
    runs_in_transaction=False,
)
```

**Update the function signature and body:**

```python
async def promote_sold_obs(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    fx_rates_repository: FxRatesRepository,
    **kwargs: Any,
) -> dict:
    """Promote unpromoted staging rows from both channels into price_observation."""
    rate_rows = await fx_rates_repository.get_rates_for_date(date.today())
    fx_map: dict[str, float] = {r["from_currency"]: r["rate"] for r in rate_rows}
    if not fx_map:
        logger.warning("promote_sold_obs_no_fx_rates", extra={"date": str(date.today())})

    own_promoted = await _promote_channel(
        staging_rows=await ebay_sales_repository.get_unpromoted(),
        mark_fn=lambda ids: ebay_sales_repository.mark_promoted(ids),
        upsert_fn=ebay_sales_repository.upsert_price_observation,
        fx_map=None,  # own-sales are always USD
    )
    scrape_promoted = await _promote_channel(
        staging_rows=await ebay_scrape_repository.get_unpromoted(),
        mark_fn=lambda ids: ebay_scrape_repository.mark_promoted(ids),
        upsert_fn=ebay_sales_repository.upsert_price_observation,
        fx_map=fx_map or None,  # None when empty → face-value fallback
    )
    total = own_promoted + scrape_promoted
    logger.info(
        "ebay_promote_sold_obs_complete",
        extra={"own_promoted": own_promoted, "scrape_promoted": scrape_promoted},
    )
    return {"promoted": total}
```

- [ ] **Step 4: Update the existing `test_promote_sold_obs_both_channels` test to pass `fx_rates_repository`**

The existing test now needs the new parameter. Find this test:

```python
@pytest.mark.asyncio
async def test_promote_sold_obs_both_channels():
    ebay_sales = AsyncMock()
    ...
    ebay_scrape = AsyncMock()
    ...
    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
    )
```

Update it to pass a minimal `fx_rates_repository`:

```python
@pytest.mark.asyncio
async def test_promote_sold_obs_both_channels():
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[_row(1, 200)])
    ebay_sales.mark_promoted = AsyncMock()
    ebay_sales.upsert_price_observation = AsyncMock()

    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[_scrape_row(10, 300)])
    ebay_scrape.mark_promoted = AsyncMock()

    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[])

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

    assert result["promoted"] == 2
    assert ebay_sales.upsert_price_observation.call_count == 2


@pytest.mark.asyncio
async def test_promote_sold_obs_empty_both():
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[])
    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[])
    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[])

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )
    assert result == {"promoted": 0}
```

- [ ] **Step 5: Run all promote_sold_obs tests**

```bash
pytest tests/unit/core/services/ebay/test_promote_sold_obs_service.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run the full unit test suite to catch regressions**

```bash
pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: green, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py \
        tests/unit/core/services/ebay/test_promote_sold_obs_service.py
git commit -m "feat(ebay): wire FX rates into promote_sold_obs — AUD/CAD scrape prices now USD-normalised"
```

---

## Post-Implementation Verification

- [ ] **Verify FX rates are populated in the DB** (requires 06:45 AEST beat to have run at least once):

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT rate_date, from_currency, to_currency, rate
FROM pricing.fx_rates
ORDER BY rate_date DESC, from_currency
LIMIT 10;
"
```

Expected: rows for AUD→USD and CAD→USD for recent dates.

- [ ] **Update backlog docs**

Mark C3/P4 as resolved in `docs/MASTER_TECHNICAL_DEBT.md` and `docs/pipelines/EBAY_GLOBAL_MARKET_SCRAPER.md` Known Limitations section.

```bash
git add docs/MASTER_TECHNICAL_DEBT.md docs/pipelines/EBAY_GLOBAL_MARKET_SCRAPER.md
git commit -m "docs: mark C1 and C3 resolved in master debt backlog"
```
