# Listing Price Trend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given an active eBay listing, fetch 90 days of historical price data for that card's exact condition+finish, compute 7/30/90-day trend deltas, and return a `UP/SIDEWAYS/DOWN` signal plus an enriched `raise/lower/hold/draft` recommendation.

**Architecture:** New `get_listing_meta()` on `EbaySalesRepository` resolves `item_id → card_version_id + finish_id + condition_id`. New `get_price_history()` on `PricingTierRepository` fetches `print_price_daily` (best-available source: prefer TCGPlayer, fall back to most-data). Pure `compute_price_trend()` function computes deltas and classifies signal. Existing `compute_recommendation()` gains an optional `price_trend` overlay. New registered service + `GET /{item_id}/trend` endpoint wire it together.

**Tech Stack:** Python 3.11, asyncpg, FastAPI, pytest (asyncio_mode=auto), TimescaleDB `print_price_daily`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/automana/core/repositories/app_integration/ebay/sales_queries.py` | Add `GET_LISTING_META` SQL |
| Modify | `src/automana/core/repositories/app_integration/ebay/sales_repository.py` | Add `get_listing_meta()` |
| Modify | `src/automana/core/repositories/pricing/price_repository.py` | Add `get_price_history()` |
| Modify | `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py` | Add `PriceTrend`, `compute_price_trend()`, trend overlay in `compute_recommendation()` |
| Create | `src/automana/core/services/app_integration/ebay/price_trend_service.py` | Registered service `integrations.ebay.recommendations.trend` |
| Modify | `src/automana/api/routers/integrations/ebay/ebay_recommendations.py` | Add `GET /{item_id}/trend` |
| Create | `tests/unit/core/test_compute_price_trend.py` | Unit tests for `compute_price_trend()` and the trend overlay in `compute_recommendation()` |
| Create | `tests/unit/core/test_price_trend_service.py` | Unit tests for `get_listing_price_trend` service |

---

## Task 1: Add `GET_LISTING_META` SQL and `get_listing_meta()` to EbaySalesRepository

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/sales_queries.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/sales_repository.py`

The query uses `COALESCE` to fall back to schema default IDs when `finish_id`/`condition_id` are NULL (pre-migration_37 rows).

- [ ] **Step 1: Add the SQL constant to `sales_queries.py`**

Append after the last existing constant:

```python
GET_LISTING_META = """
SELECT
    eal.card_version_id,
    COALESCE(eal.finish_id,    pricing.default_finish_id())    AS finish_id,
    COALESCE(eal.condition_id, pricing.default_condition_id()) AS condition_id,
    COALESCE(eal.language_id,  card_catalog.default_language_id()) AS language_id,
    cf.code  AS finish_code,
    cc.code  AS condition_code
FROM app_integration.ebay_active_listings eal
JOIN card_catalog.card_finished   cf ON cf.finish_id    = COALESCE(eal.finish_id,    pricing.default_finish_id())
JOIN pricing.card_condition       cc ON cc.condition_id = COALESCE(eal.condition_id, pricing.default_condition_id())
WHERE eal.item_id  = $1
  AND eal.app_code = $2
"""
```

- [ ] **Step 2: Add `get_listing_meta()` to `sales_repository.py`**

Add at the end of the `EbaySalesRepository` class, before the final closing brace:

```python
async def get_listing_meta(self, item_id: str, app_code: str) -> Optional[dict]:
    """Fetch card_version_id + finish/condition IDs for an active listing.

    Returns None if the listing does not exist or card_version_id is NULL.
    """
    rows = await self.execute_query(
        sales_queries.GET_LISTING_META,
        (item_id, app_code),
    )
    if not rows:
        return None
    row = dict(rows[0])
    if row["card_version_id"] is None:
        return None
    return row
```

- [ ] **Step 3: Write the failing unit test**

Create `tests/unit/core/test_compute_price_trend.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest


async def test_get_listing_meta_returns_none_for_missing_item():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[])

    result = await repo.get_listing_meta("missing-item", "myapp")

    assert result is None


async def test_get_listing_meta_returns_dict_for_existing_item():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    card_id = uuid4()
    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[{
        "card_version_id": card_id,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    }])

    result = await repo.get_listing_meta("item-123", "myapp")

    assert result["card_version_id"] == card_id
    assert result["finish_code"] == "NONFOIL"
    assert result["condition_code"] == "NM"


async def test_get_listing_meta_returns_none_when_card_version_id_is_null():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[{
        "card_version_id": None,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    }])

    result = await repo.get_listing_meta("item-123", "myapp")

    assert result is None
```

- [ ] **Step 4: Run tests (expect failure — method doesn't exist yet)**

```bash
cd /home/arthur/projects/AutoMana && docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py::test_get_listing_meta_returns_none_for_missing_item tests/unit/core/test_compute_price_trend.py::test_get_listing_meta_returns_dict_for_existing_item tests/unit/core/test_compute_price_trend.py::test_get_listing_meta_returns_none_when_card_version_id_is_null -v
```

Expected: 3 failures (ImportError or AttributeError)

- [ ] **Step 5: Apply the changes from Steps 1 and 2, then re-run**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py::test_get_listing_meta_returns_none_for_missing_item tests/unit/core/test_compute_price_trend.py::test_get_listing_meta_returns_dict_for_existing_item tests/unit/core/test_compute_price_trend.py::test_get_listing_meta_returns_none_when_card_version_id_is_null -v
```

Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/sales_queries.py \
        src/automana/core/repositories/app_integration/ebay/sales_repository.py \
        tests/unit/core/test_compute_price_trend.py
git commit -m "feat(listings): add get_listing_meta to EbaySalesRepository"
```

---

## Task 2: Add `get_price_history()` to `PricingTierRepository`

**Files:**
- Modify: `src/automana/core/repositories/pricing/price_repository.py`
- Test: `tests/unit/core/test_compute_price_trend.py` (append)

- [ ] **Step 1: Add the SQL constant to `price_repository.py`**

Append near the top of the file with the other SQL constants:

```python
_GET_PRICE_HISTORY_SQL = """
WITH source_priority AS (
    SELECT
        ppd.source_id,
        ps.code,
        COUNT(*)                                      AS n_rows,
        CASE WHEN ps.code = 'tcg' THEN 0 ELSE 1 END  AS preferred
    FROM pricing.print_price_daily ppd
    JOIN pricing.price_source ps USING (source_id)
    WHERE ppd.card_version_id = $1
      AND ppd.finish_id       = $2
      AND ppd.condition_id    = $3
      AND ppd.price_date      >= CURRENT_DATE - make_interval(days => $4)
    GROUP BY ppd.source_id, ps.code
    ORDER BY preferred, n_rows DESC
    LIMIT 1
),
best AS (SELECT source_id, code AS source_code FROM source_priority)
SELECT
    ppd.price_date,
    ppd.list_avg_cents,
    ppd.list_low_cents,
    best.source_code
FROM pricing.print_price_daily ppd
JOIN best USING (source_id)
WHERE ppd.card_version_id = $1
  AND ppd.finish_id       = $2
  AND ppd.condition_id    = $3
  AND ppd.price_date      >= CURRENT_DATE - make_interval(days => $4)
ORDER BY ppd.price_date ASC
"""
```

- [ ] **Step 2: Add `get_price_history()` to `PricingTierRepository`**

Add after `get_card_current_prices()`:

```python
async def get_price_history(
    self,
    card_version_id,
    finish_id: int,
    condition_id: int,
    days: int = 90,
) -> list[dict]:
    """Return daily price series for a card variant over the last `days` days.

    Uses best-available source: prefers TCGPlayer ('tcg'), falls back to the
    source with the most observations for this card+finish+condition window.

    Returns list of dicts sorted oldest-first. Empty list if no data.
    """
    rows = await self.connection.fetch(
        _GET_PRICE_HISTORY_SQL,
        card_version_id,
        finish_id,
        condition_id,
        days,
    )
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Append tests to `tests/unit/core/test_compute_price_trend.py`**

```python
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
from uuid import uuid4


async def test_get_price_history_returns_empty_list_when_no_data():
    from automana.core.repositories.pricing.price_repository import PricingTierRepository

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    repo = PricingTierRepository(connection=mock_conn)

    result = await repo.get_price_history(uuid4(), finish_id=1, condition_id=1, days=90)

    assert result == []


async def test_get_price_history_returns_sorted_dicts():
    from automana.core.repositories.pricing.price_repository import PricingTierRepository

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[
        {"price_date": date(2026, 4, 1), "list_avg_cents": 1000, "list_low_cents": 900, "source_code": "tcg"},
        {"price_date": date(2026, 5, 1), "list_avg_cents": 1200, "list_low_cents": 1100, "source_code": "tcg"},
    ])
    repo = PricingTierRepository(connection=mock_conn)

    result = await repo.get_price_history(uuid4(), finish_id=1, condition_id=1, days=90)

    assert len(result) == 2
    assert result[0]["price_date"] == date(2026, 4, 1)
    assert result[1]["list_avg_cents"] == 1200
    assert result[0]["source_code"] == "tcg"
```

- [ ] **Step 4: Run new tests (expect failure)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py::test_get_price_history_returns_empty_list_when_no_data tests/unit/core/test_compute_price_trend.py::test_get_price_history_returns_sorted_dicts -v
```

Expected: 2 failures (AttributeError — method not yet added)

- [ ] **Step 5: Apply Step 1 and Step 2 changes, re-run**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/pricing/price_repository.py \
        tests/unit/core/test_compute_price_trend.py
git commit -m "feat(pricing): add get_price_history to PricingTierRepository"
```

---

## Task 3: Add `PriceTrend` dataclass and `compute_price_trend()` pure function

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py`
- Test: `tests/unit/core/test_compute_price_trend.py` (append)

- [ ] **Step 1: Add imports and `PriceTrend` dataclass**

In `listing_recommendation_service.py`, update the imports block at the top:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Optional
from uuid import UUID

from automana.core.framework.registry import ServiceRegistry
from automana.core.services.analytics.strategies import (
    CompetitiveStrategy,
    PremiumStrategy,
    PricingStrategyManager,
    QuickSaleStrategy,
)
```

Then add the `PriceTrend` dataclass right after the existing `ListingRecommendation` dataclass:

```python
@dataclass
class PriceTrend:
    signal: Literal["UP", "DOWN", "SIDEWAYS", "INSUFFICIENT_DATA"]
    delta_7d_pct: Optional[float]
    delta_30d_pct: Optional[float]
    delta_90d_pct: Optional[float]
    latest_avg_cents: Optional[int]
    n_observations: int
    source_used: Optional[str]
```

- [ ] **Step 2: Add `compute_price_trend()` pure function**

Add after the `PriceTrend` dataclass and before `compute_recommendation()`:

```python
def _delta_pct(series: list[dict], latest_date: date, window_days: int) -> Optional[float]:
    """% change between the anchor (oldest point on or before latest_date - window_days) and latest."""
    cutoff = latest_date - timedelta(days=window_days)
    candidates = [r for r in series if r["price_date"] <= cutoff]
    if not candidates:
        return None
    anchor = candidates[-1]["list_avg_cents"]
    latest = series[-1]["list_avg_cents"]
    if not anchor:
        return None
    return round((latest - anchor) / anchor * 100, 2)


def compute_price_trend(price_series: list[dict]) -> PriceTrend:
    """Classify a historical price series into a trend signal.

    Args:
        price_series: list of dicts with keys price_date (date), list_avg_cents (int),
                      list_low_cents (int), source_code (str). Must be sorted oldest-first.
    """
    n = len(price_series)
    if n < 2:
        return PriceTrend(
            signal="INSUFFICIENT_DATA",
            delta_7d_pct=None,
            delta_30d_pct=None,
            delta_90d_pct=None,
            latest_avg_cents=price_series[-1]["list_avg_cents"] if n == 1 else None,
            n_observations=n,
            source_used=price_series[-1]["source_code"] if n == 1 else None,
        )

    latest_date: date = price_series[-1]["price_date"]
    latest_avg: int = price_series[-1]["list_avg_cents"]
    source: str = price_series[-1]["source_code"]

    d7  = _delta_pct(price_series, latest_date, 7)
    d30 = _delta_pct(price_series, latest_date, 30)
    d90 = _delta_pct(price_series, latest_date, 90)

    # Primary signal: 30-day delta; fallback: 7-day
    primary = d30 if d30 is not None else d7
    if primary is None:
        signal: Literal["UP", "DOWN", "SIDEWAYS", "INSUFFICIENT_DATA"] = "INSUFFICIENT_DATA"
    elif primary >= 10.0:
        signal = "UP"
    elif primary <= -10.0:
        signal = "DOWN"
    else:
        signal = "SIDEWAYS"

    return PriceTrend(
        signal=signal,
        delta_7d_pct=d7,
        delta_30d_pct=d30,
        delta_90d_pct=d90,
        latest_avg_cents=latest_avg,
        n_observations=n,
        source_used=source,
    )
```

- [ ] **Step 3: Write failing tests for `compute_price_trend()`**

Append to `tests/unit/core/test_compute_price_trend.py`:

```python
from datetime import date, timedelta


def _make_series(n_days: int, start_cents: int, end_cents: int, source: str = "tcg") -> list[dict]:
    """Generate a linear price series from start to end over n_days."""
    today = date(2026, 5, 17)
    series = []
    for i in range(n_days):
        day = today - timedelta(days=n_days - 1 - i)
        price = int(start_cents + (end_cents - start_cents) * i / max(n_days - 1, 1))
        series.append({"price_date": day, "list_avg_cents": price, "list_low_cents": price - 50, "source_code": source})
    return series


def test_compute_price_trend_insufficient_data_empty():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    result = compute_price_trend([])
    assert result.signal == "INSUFFICIENT_DATA"
    assert result.n_observations == 0
    assert result.delta_30d_pct is None


def test_compute_price_trend_insufficient_data_single_row():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(1, 1000, 1000)
    result = compute_price_trend(series)
    assert result.signal == "INSUFFICIENT_DATA"
    assert result.n_observations == 1
    assert result.latest_avg_cents == 1000


def test_compute_price_trend_up_signal():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    # +20% over 35 days — 30d delta should be >= 10%
    series = _make_series(35, 1000, 1200)
    result = compute_price_trend(series)
    assert result.signal == "UP"
    assert result.delta_30d_pct is not None
    assert result.delta_30d_pct >= 10.0


def test_compute_price_trend_down_signal():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    # -20% over 35 days
    series = _make_series(35, 1200, 1000)
    result = compute_price_trend(series)
    assert result.signal == "DOWN"
    assert result.delta_30d_pct is not None
    assert result.delta_30d_pct <= -10.0


def test_compute_price_trend_sideways_signal():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    # +5% over 35 days — within ±10% band
    series = _make_series(35, 1000, 1050)
    result = compute_price_trend(series)
    assert result.signal == "SIDEWAYS"


def test_compute_price_trend_falls_back_to_7d_when_no_30d_anchor():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    # Only 10 days of data — 30d window has no anchor
    series = _make_series(10, 1000, 1200)
    result = compute_price_trend(series)
    assert result.delta_30d_pct is None
    assert result.delta_7d_pct is not None
    # Signal derived from 7d
    assert result.signal in ("UP", "DOWN", "SIDEWAYS")


def test_compute_price_trend_sets_source_and_latest_cents():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(35, 1000, 1200, source="cardkingdom")
    result = compute_price_trend(series)
    assert result.source_used == "cardkingdom"
    assert result.latest_avg_cents == 1200
```

- [ ] **Step 4: Run tests (expect failure — compute_price_trend not yet added)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py -k "trend" -v
```

Expected: failures (ImportError)

- [ ] **Step 5: Apply Step 1 and Step 2 changes, re-run**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/listing_recommendation_service.py \
        tests/unit/core/test_compute_price_trend.py
git commit -m "feat(trend): add PriceTrend dataclass and compute_price_trend()"
```

---

## Task 4: Extend `compute_recommendation()` with trend overlay

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py`
- Test: `tests/unit/core/test_compute_price_trend.py` (append)

- [ ] **Step 1: Add trend overlay logic to `compute_recommendation()`**

Replace the existing `compute_recommendation()` signature and body:

```python
_TREND_ADJUSTER: dict[tuple[str, str], tuple[str, float]] = {
    ("hold",  "UP"):   ("raise", +0.05),
    ("hold",  "DOWN"): ("lower", +0.05),
    ("raise", "DOWN"): ("hold",  -0.05),
    ("lower", "UP"):   ("hold",  -0.05),
}


def compute_recommendation(
    signals: dict,
    market_data: dict | None = None,
    price_trend: PriceTrend | None = None,
) -> ListingRecommendation:
    """Pure recommendation engine — no DB access. Safe to call from router or agent tool."""
    days_listed = signals.get('days_listed', 0)
    watch_count = signals.get('watch_count', 0)
    price = signals.get('price', 0.0)

    if market_data is None:
        rec = _behavioral_recommendation(days_listed, watch_count)
    else:
        rec = _market_recommendation(days_listed, price, market_data)

    if price_trend is None or price_trend.signal in ("SIDEWAYS", "INSUFFICIENT_DATA"):
        return rec

    # Apply trend overlay — draft is always preserved
    if rec.suggested_action == "draft":
        return rec

    key = (rec.suggested_action, price_trend.signal)
    if key in _TREND_ADJUSTER:
        new_action, confidence_delta = _TREND_ADJUSTER[key]
        return ListingRecommendation(
            suggested_action=new_action,  # type: ignore[arg-type]
            strategy_kind=rec.strategy_kind,
            suggested_price=rec.suggested_price,
            confidence=max(0.0, min(1.0, rec.confidence + confidence_delta)),
            signals_used="trend",
            all_strategies=rec.all_strategies,
        )

    # Trend agrees with existing action — boost confidence
    return ListingRecommendation(
        suggested_action=rec.suggested_action,
        strategy_kind=rec.strategy_kind,
        suggested_price=rec.suggested_price,
        confidence=max(0.0, min(1.0, rec.confidence + 0.05)),
        signals_used="trend",
        all_strategies=rec.all_strategies,
    )
```

- [ ] **Step 2: Write failing tests for the trend overlay**

Append to `tests/unit/core/test_compute_price_trend.py`:

```python
from automana.core.services.app_integration.ebay.listing_recommendation_service import (
    PriceTrend,
    compute_recommendation,
)


def _trend(signal: str) -> PriceTrend:
    return PriceTrend(
        signal=signal,  # type: ignore[arg-type]
        delta_7d_pct=None, delta_30d_pct=None, delta_90d_pct=None,
        latest_avg_cents=1000, n_observations=30, source_used="tcg",
    )


def test_trend_overlay_hold_up_becomes_raise():
    # Behavioral: 3 days listed, 6 watches → raise; but let's force hold first
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("UP"))
    # Behavioral gives 'hold' (10 days, 1 watch → not yet at 14-day threshold)
    assert rec.suggested_action == "raise"
    assert rec.signals_used == "trend"


def test_trend_overlay_hold_down_becomes_lower():
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("DOWN"))
    assert rec.suggested_action == "lower"
    assert rec.signals_used == "trend"


def test_trend_overlay_draft_unchanged():
    signals = {"days_listed": 35, "watch_count": 0, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("UP"))
    assert rec.suggested_action == "draft"


def test_trend_overlay_sideways_leaves_action_unchanged():
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec_no_trend = compute_recommendation(signals)
    rec_sideways = compute_recommendation(signals, price_trend=_trend("SIDEWAYS"))
    assert rec_sideways.suggested_action == rec_no_trend.suggested_action
    assert rec_sideways.signals_used == rec_no_trend.signals_used


def test_trend_overlay_insufficient_data_leaves_action_unchanged():
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec_no_trend = compute_recommendation(signals)
    rec = compute_recommendation(signals, price_trend=_trend("INSUFFICIENT_DATA"))
    assert rec.suggested_action == rec_no_trend.suggested_action


def test_trend_overlay_raise_down_becomes_hold():
    # 3 days listed, 6 watches → raise (behavioral)
    signals = {"days_listed": 3, "watch_count": 6, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("DOWN"))
    assert rec.suggested_action == "hold"


def test_trend_overlay_lower_up_becomes_hold():
    # >14 days, <2 watches → lower (behavioral)
    signals = {"days_listed": 20, "watch_count": 1, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("UP"))
    assert rec.suggested_action == "hold"
```

- [ ] **Step 3: Run failing tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py -k "overlay" -v
```

Expected: failures (TypeError — unexpected keyword argument `price_trend`)

- [ ] **Step 4: Apply Step 1 changes, re-run all tests in file**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_compute_price_trend.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/listing_recommendation_service.py \
        tests/unit/core/test_compute_price_trend.py
git commit -m "feat(trend): extend compute_recommendation with price_trend overlay"
```

---

## Task 5: Create `price_trend_service.py` — registered orchestration service

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/price_trend_service.py`
- Create: `tests/unit/core/test_price_trend_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/test_price_trend_service.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import date, timedelta
import pytest


def _make_series(n: int, start: int, end: int) -> list[dict]:
    today = date(2026, 5, 17)
    series = []
    for i in range(n):
        day = today - timedelta(days=n - 1 - i)
        price = int(start + (end - start) * i / max(n - 1, 1))
        series.append({"price_date": day, "list_avg_cents": price, "list_low_cents": price - 50, "source_code": "tcg"})
    return series


async def test_get_listing_price_trend_raises_for_unknown_item():
    from automana.core.services.app_integration.ebay.price_trend_service import get_listing_price_trend

    ebay_sales_repo = MagicMock()
    ebay_sales_repo.get_listing_meta = AsyncMock(return_value=None)
    pricing_repo = MagicMock()

    with pytest.raises(ValueError, match="not found"):
        await get_listing_price_trend(
            item_id="bad-item",
            app_code="myapp",
            ebay_sales_repository=ebay_sales_repo,
            pricing_repository=pricing_repo,
        )


async def test_get_listing_price_trend_returns_up_signal():
    from automana.core.services.app_integration.ebay.price_trend_service import get_listing_price_trend

    card_id = uuid4()
    ebay_sales_repo = MagicMock()
    ebay_sales_repo.get_listing_meta = AsyncMock(return_value={
        "card_version_id": card_id,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    })
    pricing_repo = MagicMock()
    pricing_repo.get_price_history = AsyncMock(return_value=_make_series(35, 1000, 1250))

    result = await get_listing_price_trend(
        item_id="item-123",
        app_code="myapp",
        ebay_sales_repository=ebay_sales_repo,
        pricing_repository=pricing_repo,
    )

    assert result["trend"]["signal"] == "UP"
    assert result["item_id"] == "item-123"
    assert result["finish"] == "NONFOIL"
    assert result["condition"] == "NM"
    assert result["recommendation"]["suggested_action"] in ("raise", "hold", "lower", "draft")


async def test_get_listing_price_trend_returns_insufficient_data_for_empty_history():
    from automana.core.services.app_integration.ebay.price_trend_service import get_listing_price_trend

    card_id = uuid4()
    ebay_sales_repo = MagicMock()
    ebay_sales_repo.get_listing_meta = AsyncMock(return_value={
        "card_version_id": card_id,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    })
    pricing_repo = MagicMock()
    pricing_repo.get_price_history = AsyncMock(return_value=[])

    result = await get_listing_price_trend(
        item_id="item-123",
        app_code="myapp",
        ebay_sales_repository=ebay_sales_repo,
        pricing_repository=pricing_repo,
    )

    assert result["trend"]["signal"] == "INSUFFICIENT_DATA"
    assert result["trend"]["n_observations"] == 0
```

- [ ] **Step 2: Run tests (expect failure)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_price_trend_service.py -v
```

Expected: failures (ImportError)

- [ ] **Step 3: Create `price_trend_service.py`**

Create `src/automana/core/services/app_integration/ebay/price_trend_service.py`:

```python
from __future__ import annotations

import logging
from uuid import UUID

from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay.listing_recommendation_service import (
    PriceTrend,
    compute_price_trend,
    compute_recommendation,
)

logger = logging.getLogger(__name__)


async def get_listing_price_trend(
    item_id: str,
    app_code: str,
    ebay_sales_repository,
    pricing_repository,
) -> dict:
    """Orchestrate listing meta fetch → price history → trend → recommendation."""
    meta = await ebay_sales_repository.get_listing_meta(item_id, app_code)
    if meta is None:
        raise ValueError(f"Listing {item_id!r} not found or not yet linked to a card")

    card_version_id: UUID = meta["card_version_id"]
    finish_id: int = meta["finish_id"]
    condition_id: int = meta["condition_id"]

    history = await pricing_repository.get_price_history(
        card_version_id, finish_id, condition_id, days=90
    )

    trend: PriceTrend = compute_price_trend(history)

    signals = {"days_listed": 0, "watch_count": 0, "price": (trend.latest_avg_cents or 0) / 100}
    rec = compute_recommendation(signals, price_trend=trend)

    logger.info(
        "Price trend computed",
        extra={
            "item_id": item_id,
            "signal": trend.signal,
            "action": rec.suggested_action,
            "n_observations": trend.n_observations,
        },
    )

    return {
        "item_id": item_id,
        "card_version_id": str(card_version_id),
        "finish": meta["finish_code"],
        "condition": meta["condition_code"],
        "trend": {
            "signal": trend.signal,
            "delta_7d_pct": trend.delta_7d_pct,
            "delta_30d_pct": trend.delta_30d_pct,
            "delta_90d_pct": trend.delta_90d_pct,
            "latest_avg_cents": trend.latest_avg_cents,
            "n_observations": trend.n_observations,
            "source_used": trend.source_used,
        },
        "recommendation": {
            "suggested_action": rec.suggested_action,
            "confidence": rec.confidence,
            "signals_used": rec.signals_used,
        },
    }


@ServiceRegistry.register(
    path="integrations.ebay.recommendations.trend",
    db_repositories=["pricing", "ebay_sales"],
    api_repositories=[],
)
async def _registered_get_listing_price_trend(
    item_id: str,
    app_code: str,
    pricing_repository=None,
    ebay_sales_repository=None,
) -> dict:
    return await get_listing_price_trend(
        item_id=item_id,
        app_code=app_code,
        ebay_sales_repository=ebay_sales_repository,
        pricing_repository=pricing_repository,
    )
```

- [ ] **Step 4: Re-run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/core/test_price_trend_service.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/price_trend_service.py \
        tests/unit/core/test_price_trend_service.py
git commit -m "feat(trend): add price_trend_service with ServiceRegistry registration"
```

---

## Task 6: Add `GET /{item_id}/trend` endpoint and import the service

**Files:**
- Modify: `src/automana/api/routers/integrations/ebay/ebay_recommendations.py`

- [ ] **Step 1: Add the import for the new service module**

The `ServiceRegistry.register` decorator runs at import time. Add this import near the top of `ebay_recommendations.py`, after the existing imports:

```python
import automana.core.services.app_integration.ebay.price_trend_service  # noqa: F401 — registers 'integrations.ebay.recommendations.trend'
```

- [ ] **Step 2: Add the `GET /{item_id}/trend` endpoint**

Append at the end of `ebay_recommendations.py`:

```python
@router.get("/{item_id}/trend", description="Get historical price trend and recommendation for an active eBay listing")
async def get_listing_price_trend(
    item_id: str,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.recommendations.trend",
            item_id=item_id,
            app_code=app_code,
        )
        return ApiResponse(message="Price trend retrieved", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise
```

- [ ] **Step 3: Verify the router loads without errors**

```bash
docker compose -f docker-compose.dev.yml exec backend python -c "
from automana.api.routers.integrations.ebay.ebay_recommendations import router
print('Routes:', [r.path for r in router.routes])
"
```

Expected output includes: `/{item_id}/trend`

- [ ] **Step 4: Run the full unit test suite to check no regressions**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/ -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add src/automana/api/routers/integrations/ebay/ebay_recommendations.py
git commit -m "feat(api): add GET /{item_id}/trend endpoint for listing price trend"
```

---

## Task 7: Fix spec — correct repository alias reference

The design spec erroneously references `"selling"` and `"ebay_selling"` as the `EbaySalesRepository` alias. The correct alias (from `framework/registry.py`) is `"ebay_sales"`. Update the spec for accuracy.

**Files:**
- Modify: `docs/superpowers/specs/2026-05-17-listing-price-trend-design.md`

- [ ] **Step 1: Fix alias in spec**

Replace both occurrences of the wrong alias:
- `db_repositories=["pricing", "selling"]` → `db_repositories=["pricing", "ebay_sales"]`
- `db_repositories=["pricing", "ebay_selling"]` → `db_repositories=["pricing", "ebay_sales"]`

Also update the **Files to create / modify** table — replace `ApiSelling_repository.py` with `sales_queries.py` + `sales_repository.py`.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-17-listing-price-trend-design.md
git commit -m "docs(spec): fix repository alias ebay_sales + correct file references"
```
