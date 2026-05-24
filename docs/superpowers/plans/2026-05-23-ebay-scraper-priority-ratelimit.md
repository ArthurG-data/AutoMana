# eBay Scraper Priority Rotation + Rate-Limit Tracking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add staleness-weighted priority scoring to the eBay scrape watchlist and in-memory rate-limit enforcement to `scrape_global_market`.

**Architecture:** A new `priority_score` column on `pricing.ebay_scrape_targets` stores `MAX(sell_avg_cents)` per card, populated during `refresh_scrape_targets`. `GET_SCRAPE_TARGETS` multiplies this by a staleness factor computed at query time. Rate limiting lives entirely inside `scrape_global_market` as a local counter with `for…else/break` propagation.

**Tech Stack:** PostgreSQL (SQL migration), Python asyncio, pytest-asyncio, `unittest.mock.AsyncMock`.

**Spec:** `docs/superpowers/specs/2026-05-23-ebay-scraper-priority-ratelimit-design.md`
**Issues:** Closes #291, closes #290

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `database/SQL/migrations/migration_47_ebay_scrape_targets_priority.sql` | **Create** | ADD COLUMN priority_score |
| `core/repositories/app_integration/ebay/ebay_scrape_queries.py` | **Modify** | Update REFRESH_SCRAPE_TARGETS + GET_SCRAPE_TARGETS |
| `core/services/app_integration/ebay/scrape_global_market_service.py` | **Modify** | Rate-limit counter + for…else loop refactor |
| `tests/unit/core/repositories/pricing/test_ebay_scrape_queries.py` | **Create** | SQL query string tests |
| `tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py` | **Modify** | Fix broken signature + add rate-limit tests |

---

## Task 1: Migration — Add priority_score Column

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_47_ebay_scrape_targets_priority.sql`

- [ ] **Step 1: Create the migration file**

```sql
BEGIN;

ALTER TABLE pricing.ebay_scrape_targets
    ADD COLUMN IF NOT EXISTS priority_score INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN pricing.ebay_scrape_targets.priority_score
    IS 'MAX(sold_avg_cents) from price_observation in the last 7 days. Used to weight nightly scrape order by value × staleness.';

COMMIT;
```

- [ ] **Step 2: Apply the migration locally**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -f /app/src/automana/database/SQL/migrations/migration_47_ebay_scrape_targets_priority.sql
```

Expected: `ALTER TABLE`

- [ ] **Step 3: Verify the column exists**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d pricing.ebay_scrape_targets"
```

Expected: `priority_score` column visible with type `integer`.

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_47_ebay_scrape_targets_priority.sql
git commit -m "chore(db): add priority_score column to ebay_scrape_targets — #291"
```

---

## Task 2: Update SQL Query Constants

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py`

- [ ] **Step 1: Write failing SQL query tests**

Create `tests/unit/core/repositories/pricing/test_ebay_scrape_queries.py`:

```python
from automana.core.repositories.app_integration.ebay.ebay_scrape_queries import (
    GET_SCRAPE_TARGETS,
    REFRESH_SCRAPE_TARGETS,
)


def test_get_scrape_targets_orders_by_staleness_weighted_score():
    assert "priority_score" in GET_SCRAPE_TARGETS
    assert "EXTRACT(EPOCH" in GET_SCRAPE_TARGETS
    assert "last_scraped_at" in GET_SCRAPE_TARGETS
    assert "LIMIT 500" in GET_SCRAPE_TARGETS
    assert "ORDER BY" in GET_SCRAPE_TARGETS


def test_refresh_scrape_targets_sets_priority_score():
    assert "priority_score" in REFRESH_SCRAPE_TARGETS
    assert "MAX(po.sold_avg_cents)" in REFRESH_SCRAPE_TARGETS
    assert "GROUP BY" in REFRESH_SCRAPE_TARGETS
    # ON CONFLICT must update priority_score
    assert "priority_score = EXCLUDED.priority_score" in REFRESH_SCRAPE_TARGETS
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/core/repositories/pricing/test_ebay_scrape_queries.py -v
```

Expected: FAIL — `priority_score` not yet in queries.

- [ ] **Step 3: Update GET_SCRAPE_TARGETS**

In `src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py`, replace:

```python
GET_SCRAPE_TARGETS = """
SELECT card_version_id
FROM pricing.ebay_scrape_targets
WHERE is_active = true
ORDER BY last_scraped_at NULLS FIRST
LIMIT 500;
"""
```

With:

```python
GET_SCRAPE_TARGETS = """
SELECT card_version_id
FROM pricing.ebay_scrape_targets
WHERE is_active = true
ORDER BY
    priority_score::float
    * (1 + EXTRACT(EPOCH FROM (
        now() - COALESCE(last_scraped_at, now() - INTERVAL '30 days')
    )) / 86400.0)
DESC
LIMIT 500;
"""
```

- [ ] **Step 4: Update REFRESH_SCRAPE_TARGETS**

Replace:

```python
REFRESH_SCRAPE_TARGETS = """
INSERT INTO pricing.ebay_scrape_targets (card_version_id, added_by)
SELECT DISTINCT cv.card_version_id, 'auto'
FROM card_catalog.v_card_versions_complete cv
JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
JOIN pricing.source_product sp ON sp.product_id = mcp.product_id
JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
WHERE (cv.rarity_name IN ('mythic', 'rare', 'special') OR cv.is_promo = true)
  AND po.sold_avg_cents >= $1
  AND po.ts_date >= now() - interval '7 days'
ON CONFLICT (card_version_id) DO UPDATE SET is_active = true;
"""
```

With:

```python
REFRESH_SCRAPE_TARGETS = """
INSERT INTO pricing.ebay_scrape_targets (card_version_id, added_by, priority_score)
SELECT cv.card_version_id, 'auto', MAX(po.sold_avg_cents)
FROM card_catalog.v_card_versions_complete cv
JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
JOIN pricing.source_product sp ON sp.product_id = mcp.product_id
JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
WHERE (cv.rarity_name IN ('mythic', 'rare', 'special') OR cv.is_promo = true)
  AND po.sold_avg_cents >= $1
  AND po.ts_date >= now() - interval '7 days'
GROUP BY cv.card_version_id
ON CONFLICT (card_version_id) DO UPDATE SET
    is_active = true,
    priority_score = EXCLUDED.priority_score;
"""
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/core/repositories/pricing/test_ebay_scrape_queries.py -v
```

Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py \
        tests/unit/core/repositories/pricing/test_ebay_scrape_queries.py
git commit -m "feat(ebay): staleness-weighted priority scoring for scrape target rotation — #291"
```

---

## Task 3: Fix Existing Tests Broken by Signature Change

> In the previous session, `_scrape_one_card` was changed from `source_product_id: Optional[int] = None` to `source_product_id: int`. Three existing tests call `_scrape_one_card` without passing `source_product_id` — they now fail.

**Files:**
- Modify: `tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py`

- [ ] **Step 1: Confirm the tests currently fail**

```bash
uv run pytest tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py -v
```

Expected: 3 tests fail with `TypeError: _scrape_one_card() missing 1 required keyword-only argument: 'source_product_id'` (the 4th test calls `scrape_global_market`, not `_scrape_one_card` directly, and should still pass).

- [ ] **Step 2: Add source_product_id to the three _scrape_one_card calls**

In `test_scrape_one_card_inserts_foil_nm_correctly`, `test_scrape_one_card_skips_low_score`, and `test_scrape_one_card_skips_frame_conflict`, add `source_product_id=42` to each `_scrape_one_card(...)` call:

```python
    count = await _scrape_one_card(
        card_version_id=card_version_id,
        card=card,
        app_id="APP-ID",
        marketplace="EBAY-US",
        min_date=MagicMock(),
        limit_per_card=50,
        score_threshold=0.7,
        ebay_sales_repository=sales_repo,
        ebay_scrape_repository=scrape_repo,
        ebay_finding_repository=finding_repo,
        source_product_id=42,  # add this line to all three tests
    )
```

- [ ] **Step 3: Run tests to confirm all pass**

```bash
uv run pytest tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py -v
```

Expected: 4 PASSED.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py
git commit -m "test(ebay): fix _scrape_one_card tests after source_product_id made required"
```

---

## Task 4: Rate-Limit Tracking in scrape_global_market

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py`

- [ ] **Step 1: Write failing rate-limit tests first**

Add to `tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py`:

```python
@pytest.mark.asyncio
async def test_scrape_global_market_stops_at_budget():
    """When api_calls reaches _API_DAILY_BUDGET, the outer loop breaks."""
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    # 2 cards × 3 marketplaces = 6 calls; set budget to 3 so it stops mid-way
    card_ids = [uuid4(), uuid4()]
    mock_sales = AsyncMock()
    mock_sales.ensure_product = AsyncMock(return_value=uuid4())
    mock_sales.ensure_source_product = AsyncMock(return_value=99)
    mock_scrape = AsyncMock()
    mock_scrape.get_scrape_targets = AsyncMock(return_value=card_ids)
    mock_scrape.update_target_last_scraped = AsyncMock()
    mock_card = AsyncMock()
    mock_card.get_scrape_metadata = AsyncMock(return_value={
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    })
    mock_finding = AsyncMock()
    mock_finding.find_completed_items = AsyncMock(return_value=[])

    with patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID"})(),
    ), patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service._API_DAILY_BUDGET",
        3,
    ):
        result = await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    # With budget=3, only 3 find_completed_items calls are made (not 6)
    assert mock_finding.find_completed_items.call_count == 3
    assert result["api_calls"] == 3


@pytest.mark.asyncio
async def test_scrape_global_market_warns_at_threshold(caplog):
    """A warning is logged when api_calls reaches the warn threshold."""
    import logging
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    card_ids = [uuid4()]
    mock_sales = AsyncMock()
    mock_sales.ensure_product = AsyncMock(return_value=uuid4())
    mock_sales.ensure_source_product = AsyncMock(return_value=99)
    mock_scrape = AsyncMock()
    mock_scrape.get_scrape_targets = AsyncMock(return_value=card_ids)
    mock_scrape.update_target_last_scraped = AsyncMock()
    mock_card = AsyncMock()
    mock_card.get_scrape_metadata = AsyncMock(return_value={
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    })
    mock_finding = AsyncMock()
    mock_finding.find_completed_items = AsyncMock(return_value=[])

    # Budget=5, threshold=0.80 → warn at call 4
    # 1 card × 3 marketplaces = 3 calls → no warn (3 < 4)
    # Use budget=4, threshold=0.75 → warn_at = round(4*0.75) = 3 → triggered on 3rd call
    with patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID"})(),
    ), patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service._API_DAILY_BUDGET",
        4,
    ), patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service._API_WARN_THRESHOLD",
        0.75,
    ), caplog.at_level(logging.WARNING, logger="automana.core.services.app_integration.ebay.scrape_global_market_service"):
        await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    assert any("scrape_global_market_api_budget_warning" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_scrape_global_market_result_includes_api_calls():
    """The return dict includes api_calls."""
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    mock_sales = AsyncMock()
    mock_sales.ensure_product = AsyncMock(return_value=uuid4())
    mock_sales.ensure_source_product = AsyncMock(return_value=99)
    mock_scrape = AsyncMock()
    mock_scrape.get_scrape_targets = AsyncMock(return_value=[uuid4()])
    mock_scrape.update_target_last_scraped = AsyncMock()
    mock_card = AsyncMock()
    mock_card.get_scrape_metadata = AsyncMock(return_value={
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    })
    mock_finding = AsyncMock()
    mock_finding.find_completed_items = AsyncMock(return_value=[])

    with patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID"})(),
    ):
        result = await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    assert "api_calls" in result
    assert result["api_calls"] == 3  # 1 card × 3 marketplaces
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
uv run pytest tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py::test_scrape_global_market_stops_at_budget tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py::test_scrape_global_market_warns_at_threshold tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py::test_scrape_global_market_result_includes_api_calls -v
```

Expected: 3 FAILED — `api_calls` not in result, budget not enforced.

- [ ] **Step 3: Implement rate-limit tracking in scrape_global_market_service.py**

Below the existing `_INTER_CARD_DELAY` constant, add:

```python
_API_DAILY_BUDGET = 5_000
_API_WARN_THRESHOLD = 0.80
```

Replace the body of `scrape_global_market` from the `targets` loop onward with:

```python
    min_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    total_items = 0
    api_calls = 0
    warn_at = round(_API_DAILY_BUDGET * _API_WARN_THRESHOLD)

    for card_version_id in targets:
        card = await card_repository.get_scrape_metadata(card_version_id)
        if not card:
            logger.warning(
                "scrape_global_market_card_not_found",
                extra={"card_version_id": str(card_version_id)},
            )
            continue

        product_id = await ebay_sales_repository.ensure_product(card_version_id)
        if not product_id:
            logger.warning(
                "scrape_global_market_ensure_product_failed",
                extra={"card_version_id": str(card_version_id)},
            )
            continue

        source_product_id = await ebay_sales_repository.ensure_source_product(
            card_version_id, _EBAY_SOURCE_ID
        )
        if not source_product_id:
            logger.warning(
                "scrape_global_market_ensure_source_product_failed",
                extra={"card_version_id": str(card_version_id)},
            )
            continue

        for marketplace in _MARKETPLACES:
            if api_calls >= _API_DAILY_BUDGET:
                logger.error(
                    "scrape_global_market_api_budget_exhausted",
                    extra={"api_calls": api_calls, "budget": _API_DAILY_BUDGET},
                )
                break
            api_calls += 1
            if api_calls == warn_at:
                logger.warning(
                    "scrape_global_market_api_budget_warning",
                    extra={"api_calls": api_calls, "budget": _API_DAILY_BUDGET},
                )
            try:
                count = await _scrape_one_card(
                    card_version_id=card_version_id,
                    card=card,
                    app_id=app_id,
                    marketplace=marketplace,
                    min_date=min_date,
                    limit_per_card=limit_per_card,
                    score_threshold=score_threshold,
                    ebay_sales_repository=ebay_sales_repository,
                    ebay_scrape_repository=ebay_scrape_repository,
                    ebay_finding_repository=ebay_finding_repository,
                    source_product_id=source_product_id,
                )
                total_items += count
            except Exception:
                logger.exception(
                    "scrape_global_market_card_marketplace_failed",
                    extra={
                        "card_version_id": str(card_version_id),
                        "marketplace": marketplace,
                    },
                )
            await asyncio.sleep(_INTER_MARKETPLACE_DELAY)
        else:
            # inner loop completed without hitting budget limit
            try:
                await ebay_scrape_repository.update_target_last_scraped(card_version_id)
            except Exception:
                logger.warning(
                    "scrape_global_market_update_last_scraped_failed",
                    extra={"card_version_id": str(card_version_id)},
                )
            await asyncio.sleep(_INTER_CARD_DELAY)
            continue
        break  # budget exhausted — exit outer loop

    logger.info(
        "scrape_global_market_complete",
        extra={"scraped_items": total_items, "cards_processed": len(targets), "api_calls": api_calls},
    )
    return {"scraped_items": total_items, "cards_processed": len(targets), "api_calls": api_calls}
```

- [ ] **Step 4: Run all service tests**

```bash
uv run pytest tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py -v
```

Expected: 7 PASSED (4 original + 3 new).

- [ ] **Step 5: Run the full test suite to catch regressions**

```bash
uv run pytest -v --tb=short
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/scrape_global_market_service.py \
        tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py
git commit -m "feat(ebay): in-memory Finding API rate-limit tracking in scrape_global_market — #290"
```

---

## Task 5: Close Issues + Push

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/2026-05-23-session
```

- [ ] **Step 2: Close issues**

```bash
gh issue close 291 --comment "Implemented in this session: priority_score column (migration_47), staleness-weighted ORDER BY in GET_SCRAPE_TARGETS, priority_score populated in REFRESH_SCRAPE_TARGETS. High-value cards dominate but staleness factor (days since scraped) ensures full rotation."
gh issue close 290 --comment "Implemented in this session: _API_DAILY_BUDGET=5000, _API_WARN_THRESHOLD=0.80 constants. In-memory counter per run; warning at 4000 calls, hard stop + error log at 5000. api_calls returned in service result and completion log."
```

- [ ] **Step 3: Open a PR against dev**

```bash
gh pr create \
  --base dev \
  --title "feat(ebay): scraper priority rotation + Finding API rate-limit tracking" \
  --body "$(cat <<'EOF'
# Summary

Addresses two gaps in the nightly eBay global market scraper:

1. **#291 — Watchlist rotation:** Adds `priority_score` (= `MAX(sell_avg_cents)`) to `pricing.ebay_scrape_targets`. `GET_SCRAPE_TARGETS` now ranks by `priority_score × (1 + days_since_scraped)` so high-value cards are always near the front but staleness compounds, guaranteeing eventual full rotation across all 21k targets.

2. **#290 — Rate-limit tracking:** `scrape_global_market` counts Finding API calls with an in-memory counter. Warns at 80% of the 5,000/day free-tier budget (4,000 calls), stops cleanly at 100% using Python `for…else/break` propagation. `api_calls` is included in the completion log and return dict.

---

# Related Issues
Closes #291
Closes #290

---

# Changes Introduced
- `migration_47_ebay_scrape_targets_priority.sql` — ADD COLUMN priority_score
- `ebay_scrape_queries.py` — REFRESH_SCRAPE_TARGETS uses GROUP BY + MAX; GET_SCRAPE_TARGETS orders by staleness-weighted score
- `scrape_global_market_service.py` — rate-limit counter, for…else/break loop, api_calls in result
- Tests: new SQL query tests, 3 rate-limit tests, fixed _scrape_one_card signature in existing tests

---

# How to Test
1. Apply migration_47 locally
2. Run `uv run pytest tests/unit/core/services/app_integration/ebay/ tests/unit/core/repositories/pricing/ -v`
3. Trigger a dev scrape run and confirm `scrape_global_market_complete` log includes `api_calls`

---

# Acceptance Checklist
- [ ] Code compiles without errors
- [ ] All tests pass
- [ ] Migration applied and column visible in schema
- [ ] No debug logs left behind
- [ ] Follows project coding standards
- [ ] Ready for review
EOF
)"
```
