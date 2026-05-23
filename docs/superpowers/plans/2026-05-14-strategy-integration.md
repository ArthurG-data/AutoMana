# Strategy Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing Python pricing strategies into the listings UI — per-row signal badges in the table and a full strategy advisor in the detail panel — with a staged action queue that Celery drains to eBay.

**Architecture:** A pure `compute_recommendation()` function reads listing signals (daysListed, watchCount, price) and optionally market percentiles, calls `PricingStrategyManager`, and returns a `ListingRecommendation`. A new router exposes three endpoints (get recommendation, stage action, get pending). A Celery beat task drains the `listing_pending_actions` table. The frontend fetches recommendations lazily after listing load, renders a `SignalBadge` in the table, and extends `ListingDetailPanel` with strategy cards and a stage button.

**Tech Stack:** Python/FastAPI, PostgreSQL, Celery, React 18, TypeScript, Zustand, TanStack Query, Vitest, `@testing-library/react`

**Spec:** `docs/superpowers/specs/2026-05-14-strategy-integration-design.md`

---

## File Map

### New files
| Path | Responsibility |
|------|---------------|
| `src/automana/database/SQL/migrations/migration_28_listing_pending_actions.sql` | DB table for staged actions |
| `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py` | Pure `compute_recommendation()` + registered service wrapper |
| `src/automana/core/repositories/app_integration/ebay/listing_actions_repository.py` | DB ops for `listing_pending_actions` |
| `src/automana/core/services/app_integration/ebay/listing_actions_service.py` | Thin service wrappers over the repo |
| `src/automana/api/routers/integrations/ebay/ebay_recommendations.py` | 3 new endpoints |
| `src/automana/worker/tasks/ebay_actions.py` | `drain_listing_actions` Celery task |
| `src/frontend/src/features/ebay/components/SignalBadge.tsx` | Signal badge component |
| `src/frontend/src/features/ebay/components/SignalBadge.module.css` | Badge styles |
| `src/automana/tests/unit/services/ebay/test_listing_recommendation_service.py` | Unit tests for `compute_recommendation` |
| `src/automana/tests/unit/repositories/ebay/test_listing_actions_repository.py` | Unit tests for actions repo |
| `src/frontend/src/features/ebay/components/__tests__/SignalBadge.test.tsx` | Component tests |

### Modified files
| Path | Change |
|------|--------|
| `src/automana/core/service_modules.py` | Register recommendation + action services |
| `src/automana/api/routers/integrations/ebay/__init__.py` | Include recommendations router |
| `src/automana/worker/celeryconfig.py` | Add `ebay_actions` to imports + beat schedule |
| `src/frontend/src/features/ebay/mockListings.ts` | Extend `EbayLiveListing` with `recommendation` + `pendingAction` |
| `src/frontend/src/store/listings.ts` | Add `recommendation`/`pendingAction` to store |
| `src/frontend/src/features/ebay/api.ts` | Add `fetchRecommendation`, `stageAction`, `getPendingAction` |
| `src/frontend/src/features/ebay/components/ListingsTable.tsx` | Add Signal column (COL_COUNT 10 → 11) |
| `src/frontend/src/routes/listings.tsx` | Fetch recommendations after listings load |
| `src/frontend/src/features/ebay/components/ListingDetailPanel.tsx` | Add strategy advisor section + stage button |

---

## Task 1: Database Migration

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_28_listing_pending_actions.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migration_28_listing_pending_actions.sql
-- Creates the staged listing action queue.

CREATE TABLE IF NOT EXISTS app_integration.listing_pending_actions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id         TEXT        NOT NULL,
    user_id         UUID        NOT NULL,
    app_code        TEXT        NOT NULL,
    action_type     TEXT        NOT NULL CHECK (action_type IN ('raise','lower','hold','draft')),
    strategy_kind   TEXT        NOT NULL,
    suggested_price NUMERIC(10,2),
    status          TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','done','failed')),
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_listing_actions_pending
    ON app_integration.listing_pending_actions (created_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_listing_actions_item
    ON app_integration.listing_pending_actions (item_id);

GRANT SELECT, INSERT, UPDATE ON app_integration.listing_pending_actions TO app_celery;
GRANT SELECT, INSERT, UPDATE ON app_integration.listing_pending_actions TO app_backend;
```

- [ ] **Step 2: Apply the migration**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -f /app/src/automana/database/SQL/migrations/migration_28_listing_pending_actions.sql
```

Expected: `CREATE TABLE`, `CREATE INDEX`, `CREATE INDEX`, `GRANT`, `GRANT` — no errors.

- [ ] **Step 3: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d app_integration.listing_pending_actions"
```

Expected: table with 11 columns including `id`, `item_id`, `status`, `created_at`.

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_28_listing_pending_actions.sql
git commit -m "feat(db): add listing_pending_actions migration"
```

---

## Task 2: Recommendation Service

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py`
- Create: `src/automana/tests/unit/services/ebay/test_listing_recommendation_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# src/automana/tests/unit/services/ebay/test_listing_recommendation_service.py
import pytest
from automana.core.services.app_integration.ebay.listing_recommendation_service import (
    compute_recommendation,
    ListingRecommendation,
)


def test_behavioral_draft_when_stale_no_watchers():
    rec = compute_recommendation({'days_listed': 31, 'watch_count': 0, 'price': 10.0})
    assert rec.suggested_action == 'draft'
    assert rec.signals_used == 'behavioral'
    assert rec.suggested_price is None


def test_behavioral_lower_when_stale_low_interest():
    rec = compute_recommendation({'days_listed': 15, 'watch_count': 1, 'price': 10.0})
    assert rec.suggested_action == 'lower'
    assert rec.strategy_kind == 'quick'
    assert rec.signals_used == 'behavioral'


def test_behavioral_raise_when_fresh_high_watchers():
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 6, 'price': 10.0})
    assert rec.suggested_action == 'raise'
    assert rec.strategy_kind == 'max'


def test_behavioral_hold_otherwise():
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 2, 'price': 10.0})
    assert rec.suggested_action == 'hold'
    assert rec.strategy_kind == 'balanced'


def test_market_raise_when_listed_below_p25():
    market_data = {
        'stats': {
            'median_price': 50.0, 'mean_price': 50.0, 'std_deviation': 5.0,
            'total_listings': 10, 'min_price': 30.0, 'max_price': 70.0,
            'price_range': 40.0,
        },
        'percentiles': {'p25': 40.0, 'p50': 50.0, 'p75': 60.0, 'p5': 30.0,
                        'p10': 35.0, 'p90': 65.0, 'p95': 68.0, 'p99': 70.0},
    }
    # Price $37 is below p25 ($40) * 0.95 = $38 → raise
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 2, 'price': 37.0}, market_data)
    assert rec.suggested_action == 'raise'
    assert rec.signals_used == 'market'
    assert rec.suggested_price is not None


def test_market_lower_when_listed_above_p75():
    market_data = {
        'stats': {
            'median_price': 50.0, 'mean_price': 50.0, 'std_deviation': 5.0,
            'total_listings': 10, 'min_price': 30.0, 'max_price': 70.0,
            'price_range': 40.0,
        },
        'percentiles': {'p25': 40.0, 'p50': 50.0, 'p75': 60.0, 'p5': 30.0,
                        'p10': 35.0, 'p90': 65.0, 'p95': 68.0, 'p99': 70.0},
    }
    # Price $65 is above p75 ($60) * 1.05 = $63 → lower
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 2, 'price': 65.0}, market_data)
    assert rec.suggested_action == 'lower'
    assert rec.signals_used == 'market'


def test_recommendation_is_dataclass():
    rec = compute_recommendation({'days_listed': 1, 'watch_count': 1, 'price': 10.0})
    assert isinstance(rec, ListingRecommendation)
    assert 0.0 <= rec.confidence <= 1.0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd src/automana && python -m pytest tests/unit/services/ebay/test_listing_recommendation_service.py -v
```

Expected: `ModuleNotFoundError` — `listing_recommendation_service` does not exist yet.

- [ ] **Step 3: Write the service**

```python
# src/automana/core/services/app_integration/ebay/listing_recommendation_service.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional
from uuid import UUID

from automana.core.framework.registry import ServiceRegistry
from automana.core.services.analytics.strategies import (
    CompetitiveStrategy,
    PremiumStrategy,
    PricingStrategyManager,
    QuickSaleStrategy,
)

logger = logging.getLogger(__name__)

_MANAGER = PricingStrategyManager({
    'quick': QuickSaleStrategy(),
    'balanced': CompetitiveStrategy(),
    'max': PremiumStrategy(),
})


@dataclass
class ListingRecommendation:
    suggested_action: Literal['raise', 'lower', 'hold', 'draft']
    strategy_kind: str
    suggested_price: Optional[float]
    confidence: float
    signals_used: Literal['behavioral', 'market']
    all_strategies: dict = field(default_factory=dict)


def compute_recommendation(
    signals: dict,
    market_data: dict | None = None,
) -> ListingRecommendation:
    """Pure recommendation engine — no DB access. Safe to call from router or agent tool."""
    days_listed = signals.get('days_listed', 0)
    watch_count = signals.get('watch_count', 0)
    price = signals.get('price', 0.0)

    if market_data is None:
        return _behavioral_recommendation(days_listed, watch_count)

    return _market_recommendation(days_listed, price, market_data)


def _behavioral_recommendation(days_listed: int, watch_count: int) -> ListingRecommendation:
    if days_listed > 30 and watch_count == 0:
        return ListingRecommendation(
            suggested_action='draft', strategy_kind='balanced',
            suggested_price=None, confidence=0.9, signals_used='behavioral',
        )
    if days_listed > 14 and watch_count < 2:
        return ListingRecommendation(
            suggested_action='lower', strategy_kind='quick',
            suggested_price=None, confidence=0.8, signals_used='behavioral',
        )
    if days_listed < 7 and watch_count >= 5:
        return ListingRecommendation(
            suggested_action='raise', strategy_kind='max',
            suggested_price=None, confidence=0.75, signals_used='behavioral',
        )
    return ListingRecommendation(
        suggested_action='hold', strategy_kind='balanced',
        suggested_price=None, confidence=0.7, signals_used='behavioral',
    )


def _market_recommendation(days_listed: int, price: float, market_data: dict) -> ListingRecommendation:
    stats = market_data['stats']
    percentiles = market_data['percentiles']
    p25 = percentiles.get('p25', price)
    p75 = percentiles.get('p75', price)

    market_conditions = {
        'volatility': stats.get('std_deviation', 0) / max(stats.get('mean_price', 1), 1),
        'competition_level': 'high' if stats.get('total_listings', 0) > 20 else 'medium',
        'inventory_level': 'medium',
        'cash_flow_priority': False,
        'card_rarity': market_data.get('card_rarity', 'rare'),
        'seller_reputation': 'high',
    }

    strategy_name, result = _MANAGER.recommend_strategy(market_conditions, stats, percentiles)

    if price < p25 * 0.95:
        action: Literal['raise', 'lower', 'hold', 'draft'] = 'raise'
    elif price > p75 * 1.05:
        action = 'lower'
    elif days_listed > 14 and price <= p25:
        action = 'draft'
    else:
        action = {'quick': 'lower', 'balanced': 'hold', 'max': 'raise'}.get(strategy_name, 'hold')  # type: ignore[assignment]

    all_strats = _MANAGER.get_all_strategies(stats, percentiles, market_conditions)

    return ListingRecommendation(
        suggested_action=action,
        strategy_kind=strategy_name,
        suggested_price=round(result.price, 2),
        confidence=result.confidence,
        signals_used='market',
        all_strategies={
            k: {'price': round(v.price, 2), 'description': v.description, 'confidence': v.confidence}
            for k, v in all_strats.items()
        },
    )


@ServiceRegistry.register(
    path="integrations.ebay.recommendations.get",
    db_repositories=[],
    api_repositories=[],
)
async def get_listing_recommendation(
    user_id: UUID,
    app_code: str,
    item_id: str,
    days_listed: int,
    watch_count: int,
    price: float,
    currency: str = "AUD",
) -> dict:
    signals = {
        'days_listed': days_listed,
        'watch_count': watch_count,
        'price': price,
        'currency': currency,
    }
    rec = compute_recommendation(signals, market_data=None)
    logger.info("Recommendation computed", extra={
        "item_id": item_id, "action": rec.suggested_action, "signals_used": rec.signals_used,
    })
    return {
        'item_id': item_id,
        'suggested_action': rec.suggested_action,
        'strategy_kind': rec.strategy_kind,
        'suggested_price': rec.suggested_price,
        'confidence': rec.confidence,
        'signals_used': rec.signals_used,
        'all_strategies': rec.all_strategies,
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd src/automana && python -m pytest tests/unit/services/ebay/test_listing_recommendation_service.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/listing_recommendation_service.py \
        src/automana/tests/unit/services/ebay/test_listing_recommendation_service.py
git commit -m "feat(ebay): add listing_recommendation_service with behavioral + market paths"
```

---

## Task 3: Actions Repository

**Files:**
- Create: `src/automana/core/repositories/app_integration/ebay/listing_actions_repository.py`
- Create: `src/automana/tests/unit/repositories/ebay/test_listing_actions_repository.py`

- [ ] **Step 1: Write the failing tests**

```python
# src/automana/tests/unit/repositories/ebay/test_listing_actions_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from automana.core.repositories.app_integration.ebay.listing_actions_repository import (
    EbayListingActionsRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ACTION_ID = UUID("00000000-0000-0000-0000-000000000002")


def make_repo():
    conn = MagicMock()
    repo = EbayListingActionsRepository.__new__(EbayListingActionsRepository)
    repo.connection = conn
    repo.executor = None
    return repo


@pytest.mark.asyncio
async def test_insert_action_returns_uuid():
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[{'id': str(ACTION_ID)}])

    result = await repo.insert_action(
        item_id="123456789",
        user_id=USER_ID,
        app_code="myapp",
        action_type="lower",
        strategy_kind="quick",
        suggested_price=9.99,
    )

    assert result == str(ACTION_ID)
    repo.execute_query.assert_awaited_once()
    args = repo.execute_query.call_args[0]
    assert args[1] == ("123456789", USER_ID, "myapp", "lower", "quick", 9.99)


@pytest.mark.asyncio
async def test_get_pending_returns_rows():
    repo = make_repo()
    fake_rows = [
        {'id': str(ACTION_ID), 'item_id': '111', 'user_id': str(USER_ID),
         'app_code': 'myapp', 'action_type': 'raise', 'strategy_kind': 'max',
         'suggested_price': 15.00, 'status': 'pending'}
    ]
    repo.execute_query = AsyncMock(return_value=fake_rows)

    result = await repo.get_pending(limit=50)

    assert len(result) == 1
    assert result[0]['action_type'] == 'raise'
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_done_calls_execute_command():
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)

    await repo.mark_done(action_id=ACTION_ID)

    repo.execute_command.assert_awaited_once()
    args = repo.execute_command.call_args[0]
    assert args[1][0] == ACTION_ID


@pytest.mark.asyncio
async def test_mark_failed_stores_error():
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)

    await repo.mark_failed(action_id=ACTION_ID, error="eBay timeout")

    repo.execute_command.assert_awaited_once()
    args = repo.execute_command.call_args[0]
    assert ACTION_ID in args[1]
    assert "eBay timeout" in args[1]


@pytest.mark.asyncio
async def test_get_pending_for_item_returns_first_match():
    repo = make_repo()
    fake_row = {'id': str(ACTION_ID), 'item_id': '111', 'status': 'pending'}
    repo.execute_query = AsyncMock(return_value=[fake_row])

    result = await repo.get_pending_for_item(item_id="111")

    assert result == fake_row


@pytest.mark.asyncio
async def test_get_pending_for_item_returns_none_when_empty():
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[])

    result = await repo.get_pending_for_item(item_id="999")

    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd src/automana && python -m pytest tests/unit/repositories/ebay/test_listing_actions_repository.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

```python
# src/automana/core/repositories/app_integration/ebay/listing_actions_repository.py
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_INSERT = """
INSERT INTO app_integration.listing_pending_actions
    (item_id, user_id, app_code, action_type, strategy_kind, suggested_price)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING id;
"""

_GET_PENDING = """
SELECT id, item_id, user_id, app_code, action_type, strategy_kind, suggested_price, status
FROM app_integration.listing_pending_actions
WHERE status = 'pending'
ORDER BY created_at
LIMIT $1;
"""

_MARK_PROCESSING = """
UPDATE app_integration.listing_pending_actions
SET status = 'processing'
WHERE id = $1;
"""

_MARK_DONE = """
UPDATE app_integration.listing_pending_actions
SET status = 'done', executed_at = now()
WHERE id = $1;
"""

_MARK_FAILED = """
UPDATE app_integration.listing_pending_actions
SET status = 'failed', error = $2
WHERE id = $1;
"""

_GET_PENDING_FOR_ITEM = """
SELECT id, item_id, user_id, app_code, action_type, strategy_kind, suggested_price, status
FROM app_integration.listing_pending_actions
WHERE item_id = $1 AND status IN ('pending', 'processing')
ORDER BY created_at DESC
LIMIT 1;
"""


class EbayListingActionsRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self):
        return "EbayListingActionsRepository"

    async def insert_action(
        self,
        item_id: str,
        user_id: UUID,
        app_code: str,
        action_type: str,
        strategy_kind: str,
        suggested_price: Optional[float],
    ) -> str:
        rows = await self.execute_query(_INSERT, (item_id, user_id, app_code, action_type, strategy_kind, suggested_price))
        return rows[0]['id']

    async def get_pending(self, limit: int = 50) -> list[dict]:
        rows = await self.execute_query(_GET_PENDING, (limit,))
        return list(rows)

    async def mark_processing(self, action_id: UUID) -> None:
        await self.execute_command(_MARK_PROCESSING, (action_id,))

    async def mark_done(self, action_id: UUID) -> None:
        await self.execute_command(_MARK_DONE, (action_id,))

    async def mark_failed(self, action_id: UUID, error: str) -> None:
        await self.execute_command(_MARK_FAILED, (action_id, error))

    async def get_pending_for_item(self, item_id: str) -> Optional[dict]:
        rows = await self.execute_query(_GET_PENDING_FOR_ITEM, (item_id,))
        return rows[0] if rows else None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd src/automana && python -m pytest tests/unit/repositories/ebay/test_listing_actions_repository.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Register the repository in framework/wiring.py**

In `src/automana/core/framework/registry.py`, find the `# Integration repositories` block and add:

```python
ServiceRegistry.register_db_repository(
    "listing_actions",
    "automana.core.repositories.app_integration.ebay.listing_actions_repository",
    "EbayListingActionsRepository",
)
```

- [ ] **Step 6: Verify the registry mapping**

```bash
cd src && python -c "
from automana.core.framework.registry import ServiceRegistry
entry = ServiceRegistry.get_db_repository('listing_actions')
print('Registered:', entry)
"
```

Expected: `Registered: ('automana.core.repositories.app_integration.ebay.listing_actions_repository', 'EbayListingActionsRepository')`

- [ ] **Step 7: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/listing_actions_repository.py \
        src/automana/tests/unit/repositories/ebay/test_listing_actions_repository.py \
        src/automana/core/framework/registry.py
git commit -m "feat(ebay): add EbayListingActionsRepository + registry entry"
```

---

## Task 4: Actions Service

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/listing_actions_service.py`

- [ ] **Step 1: Write the service** (thin wrappers; testing is covered by the repository tests)

```python
# src/automana/core/services/app_integration/ebay/listing_actions_service.py
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.listing_actions_repository import (
    EbayListingActionsRepository,
)
from automana.core.framework.registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.actions.stage",
    db_repositories=["listing_actions"],
    api_repositories=[],
)
async def stage_action(
    listing_actions_repository: EbayListingActionsRepository,
    user_id: UUID,
    app_code: str,
    item_id: str,
    action_type: str,
    strategy_kind: str,
    suggested_price: Optional[float] = None,
) -> dict:
    action_id = await listing_actions_repository.insert_action(
        item_id=item_id,
        user_id=user_id,
        app_code=app_code,
        action_type=action_type,
        strategy_kind=strategy_kind,
        suggested_price=suggested_price,
    )
    logger.info("Action staged", extra={
        "item_id": item_id, "action_type": action_type, "action_id": str(action_id),
    })
    return {'action_id': str(action_id), 'status': 'pending'}


@ServiceRegistry.register(
    path="integrations.ebay.actions.get_pending",
    db_repositories=["listing_actions"],
    api_repositories=[],
)
async def get_pending_action(
    listing_actions_repository: EbayListingActionsRepository,
    user_id: UUID,
    item_id: str,
) -> Optional[dict]:
    return await listing_actions_repository.get_pending_for_item(item_id=item_id)
```

- [ ] **Step 2: Verify the service imports cleanly**

```bash
cd src && python -c "from automana.core.services.app_integration.ebay.listing_actions_service import stage_action, get_pending_action; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/listing_actions_service.py
git commit -m "feat(ebay): add listing_actions_service (stage + get_pending)"
```

---

## Task 5: Recommendations Router

**Files:**
- Create: `src/automana/api/routers/integrations/ebay/ebay_recommendations.py`
- Modify: `src/automana/api/routers/integrations/ebay/__init__.py`

- [ ] **Step 1: Write the router**

```python
# src/automana/api/routers/integrations/ebay/ebay_recommendations.py
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from automana.api.dependancies.auth.users import CurrentUserDep
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import ApiResponse
from automana.core.services.app_integration.ebay.listing_recommendation_service import (
    compute_recommendation,
)

logger = logging.getLogger(__name__)

recommendations_router = APIRouter(prefix="/listings", tags=["recommendations"])


class StageActionRequest(BaseModel):
    app_code: str
    action_type: str
    strategy_kind: str
    suggested_price: Optional[float] = None


@recommendations_router.get("/{item_id}/recommendation")
async def get_recommendation(
    item_id: str,
    user: CurrentUserDep,
    days_listed: int = Query(0, ge=0),
    watch_count: int = Query(0, ge=0),
    price: float = Query(0.0, ge=0),
    currency: str = Query("AUD"),
):
    signals = {
        'days_listed': days_listed,
        'watch_count': watch_count,
        'price': price,
        'currency': currency,
    }
    rec = compute_recommendation(signals, market_data=None)
    return ApiResponse(data={
        'item_id': item_id,
        'suggested_action': rec.suggested_action,
        'strategy_kind': rec.strategy_kind,
        'suggested_price': rec.suggested_price,
        'confidence': rec.confidence,
        'signals_used': rec.signals_used,
        'all_strategies': rec.all_strategies,
    }, message="OK")


@recommendations_router.post("/{item_id}/actions")
async def stage_action(
    item_id: str,
    body: StageActionRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    if body.action_type not in ('raise', 'lower', 'hold', 'draft'):
        raise HTTPException(status_code=400, detail=f"Invalid action_type: {body.action_type}")
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.actions.stage",
            user_id=user.unique_id,
            app_code=body.app_code,
            item_id=item_id,
            action_type=body.action_type,
            strategy_kind=body.strategy_kind,
            suggested_price=body.suggested_price,
        )
        return ApiResponse(data=result, message="Action staged")
    except Exception as exc:
        logger.error("Failed to stage action", extra={"item_id": item_id, "err": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc))


@recommendations_router.get("/{item_id}/actions/pending")
async def get_pending(
    item_id: str,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    result = await service_manager.execute_service(
        "integrations.ebay.actions.get_pending",
        user_id=user.unique_id,
        item_id=item_id,
    )
    return ApiResponse(data=result, message="OK")
```

- [ ] **Step 2: Wire into the eBay router**

Open `src/automana/api/routers/integrations/ebay/__init__.py` and add:

```python
from automana.api.routers.integrations.ebay.ebay_recommendations import recommendations_router

# add to the bottom of the file:
ebay_router.include_router(recommendations_router)
```

The file should now look like:

```python
from fastapi import APIRouter
from automana.api.routers.integrations.ebay.ebay_auth import ebay_auth_router
from automana.api.routers.integrations.ebay.ebay_browse import search_router
from automana.api.routers.integrations.ebay.ebay_selling import ebay_listing_router
from automana.api.routers.integrations.ebay.scopes import router as scopes_router
from automana.api.routers.integrations.ebay.ebay_market import market_router
from automana.api.routers.integrations.ebay.ebay_recommendations import recommendations_router

ebay_router = APIRouter(prefix="/ebay", tags=["eBay"])

ebay_router.include_router(ebay_auth_router)
ebay_router.include_router(search_router)
ebay_router.include_router(ebay_listing_router)
ebay_router.include_router(scopes_router)
ebay_router.include_router(market_router)
ebay_router.include_router(recommendations_router)
```

- [ ] **Step 3: Verify the app starts without errors**

```bash
cd src && python -c "from automana.api.routers.integrations.ebay import ebay_router; print('Routes:', [r.path for r in ebay_router.routes])"
```

Expected: list of routes including `/ebay/listings/{item_id}/recommendation`.

- [ ] **Step 4: Commit**

```bash
git add src/automana/api/routers/integrations/ebay/ebay_recommendations.py \
        src/automana/api/routers/integrations/ebay/__init__.py
git commit -m "feat(ebay): add recommendation + action endpoints"
```

---

## Task 6: Register Services + Celery Drain Task

**Files:**
- Modify: `src/automana/core/service_modules.py`
- Create: `src/automana/worker/tasks/ebay_actions.py`
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 1: Register services in service_modules.py**

In `src/automana/core/service_modules.py`, add to both `"backend"` and `"celery"` lists:

```python
# Add to the "backend" list (after the last ebay service entry):
"automana.core.services.app_integration.ebay.listing_recommendation_service",
"automana.core.services.app_integration.ebay.listing_actions_service",

# Add to the "celery" list (after promote_sold_obs_service):
"automana.core.services.app_integration.ebay.listing_actions_service",
```

- [ ] **Step 2: Write the drain task**

```python
# src/automana/worker/tasks/ebay_actions.py
import logging
from celery import shared_task
from automana.worker.main import run_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="automana.worker.tasks.ebay_actions.drain_listing_actions")
def drain_listing_actions(self):
    """Process up to 50 pending listing actions.

    For raise/lower: calls the eBay listing update service.
    For draft: logs a warning (saved_drafts table not yet implemented).
    For hold: marks done immediately.
    """
    logger.info("Starting listing action drain")

    from automana.worker.ressources import get_state
    from automana.core.repositories.app_integration.ebay.listing_actions_repository import (
        EbayListingActionsRepository,
    )
    import asyncio

    state = get_state()

    async def _drain():
        async with state.db_pool.acquire() as conn:
            repo = EbayListingActionsRepository(conn, None)
            actions = await repo.get_pending(limit=50)

            processed, failed = 0, 0
            for action in actions:
                action_id = action['id']
                await repo.mark_processing(action_id)
                try:
                    if action['action_type'] in ('raise', 'lower'):
                        run_service(
                            "integrations.ebay.selling.listings.update",
                            user_id=action['user_id'],
                            app_code=action['app_code'],
                            item_id=action['item_id'],
                            start_price={
                                'currency': 'AUD',
                                'value': str(action['suggested_price']),
                            },
                        )
                    elif action['action_type'] == 'draft':
                        logger.warning(
                            "Draft action not yet executable — saved_drafts table not implemented",
                            extra={"item_id": action['item_id']},
                        )
                    # hold: nothing to do on eBay
                    await repo.mark_done(action_id)
                    processed += 1
                except Exception as exc:
                    await repo.mark_failed(action_id, str(exc))
                    logger.error("Action failed", extra={"action_id": str(action_id), "err": str(exc)})
                    failed += 1

            return {'processed': processed, 'failed': failed}

    result = asyncio.get_event_loop().run_until_complete(_drain())
    logger.info("Drain complete", extra=result)
    return result
```

- [ ] **Step 3: Add to celeryconfig.py imports and beat schedule**

In `src/automana/worker/celeryconfig.py`:

```python
# Add to the imports set:
imports = {
    "automana.worker.tasks.pipelines",
    "automana.worker.tasks.analytics",
    "automana.worker.tasks.pricing",
    "automana.worker.tasks.ebay_actions",   # ← add this line
}

# Add to beat_schedule dict:
"drain-listing-actions": {
    "task": "automana.worker.tasks.ebay_actions.drain_listing_actions",
    "schedule": crontab(minute="*/5"),  # every 5 minutes
},
```

- [ ] **Step 4: Verify import**

```bash
cd src && python -c "from automana.worker.tasks.ebay_actions import drain_listing_actions; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/service_modules.py \
        src/automana/worker/tasks/ebay_actions.py \
        src/automana/worker/celeryconfig.py
git commit -m "feat(celery): add drain_listing_actions task + register action services"
```

---

## Task 7: Frontend Types + API Functions

**Files:**
- Modify: `src/frontend/src/features/ebay/mockListings.ts`
- Modify: `src/frontend/src/store/listings.ts`
- Modify: `src/frontend/src/features/ebay/api.ts`

- [ ] **Step 1: Extend EbayLiveListing in mockListings.ts**

Add these two interfaces and extend `EbayLiveListing` (at the end of the interface block, before the closing `}`):

```typescript
// Add these interfaces before EbayLiveListing:
export interface ListingRecommendation {
  item_id: string
  suggested_action: 'raise' | 'lower' | 'hold' | 'draft'
  strategy_kind: 'quick' | 'balanced' | 'max' | 'auction7' | 'auctionReserve'
  suggested_price: number | null
  confidence: number
  signals_used: 'behavioral' | 'market'
  all_strategies: Record<string, { price: number; description: string; confidence: number }>
}

export interface PendingAction {
  action_id: string
  action_type: 'raise' | 'lower' | 'hold' | 'draft'
  strategy_kind: string
  suggested_price: number | null
  status: 'pending' | 'processing' | 'done' | 'failed'
}
```

Then extend `EbayLiveListing` (add after the last field `appName: string`):

```typescript
  recommendation?: ListingRecommendation
  pendingAction?: PendingAction
```

- [ ] **Step 2: Update listings store to expose updateRecommendation**

Replace the contents of `src/frontend/src/store/listings.ts`:

```typescript
import { create } from 'zustand'
import type { EbayLiveListing, ListingRecommendation, PendingAction } from '../features/ebay/mockListings'

interface ListingsState {
  listings: EbayLiveListing[]
  setListings: (listings: EbayLiveListing[]) => void
  getById: (itemId: string) => EbayLiveListing | undefined
  updateListing: (itemId: string, patch: Partial<EbayLiveListing>) => void
  setRecommendation: (itemId: string, rec: ListingRecommendation) => void
  setPendingAction: (itemId: string, action: PendingAction | undefined) => void
}

export const useListingsStore = create<ListingsState>()((set, get) => ({
  listings: [],
  setListings: (listings) => set({ listings }),
  getById: (itemId) => get().listings.find((l) => l.itemId === itemId),
  updateListing: (itemId, patch) =>
    set((state) => ({
      listings: state.listings.map((l) =>
        l.itemId === itemId ? { ...l, ...patch } : l
      ),
    })),
  setRecommendation: (itemId, rec) =>
    set((state) => ({
      listings: state.listings.map((l) =>
        l.itemId === itemId ? { ...l, recommendation: rec } : l
      ),
    })),
  setPendingAction: (itemId, action) =>
    set((state) => ({
      listings: state.listings.map((l) =>
        l.itemId === itemId ? { ...l, pendingAction: action } : l
      ),
    })),
}))
```

- [ ] **Step 3: Add API functions to api.ts**

Append to `src/frontend/src/features/ebay/api.ts`:

```typescript
// ── Recommendations ───────────────────────────────────────────────────────

export interface StageActionRequest {
  app_code: string
  action_type: 'raise' | 'lower' | 'draft'
  strategy_kind: string
  suggested_price: number | null
}

export async function fetchRecommendation(
  itemId: string,
  daysListed: number,
  watchCount: number,
  price: number,
  currency = 'AUD',
): Promise<import('./mockListings').ListingRecommendation> {
  const params = new URLSearchParams({
    days_listed: String(daysListed),
    watch_count: String(watchCount),
    price: String(price),
    currency,
  })
  const result = await apiClient<{ data: import('./mockListings').ListingRecommendation }>(
    `/integrations/ebay/listings/${itemId}/recommendation?${params}`
  )
  return result.data
}

export async function stageAction(
  itemId: string,
  body: StageActionRequest,
): Promise<import('./mockListings').PendingAction> {
  const result = await apiClient<{ data: import('./mockListings').PendingAction }>(
    `/integrations/ebay/listings/${itemId}/actions`,
    { method: 'POST', body: JSON.stringify(body) }
  )
  return result.data
}

export async function getPendingAction(
  itemId: string,
): Promise<import('./mockListings').PendingAction | null> {
  const result = await apiClient<{ data: import('./mockListings').PendingAction | null }>(
    `/integrations/ebay/listings/${itemId}/actions/pending`
  )
  return result.data
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/mockListings.ts \
        src/frontend/src/store/listings.ts \
        src/frontend/src/features/ebay/api.ts
git commit -m "feat(frontend): extend EbayLiveListing with recommendation + pendingAction fields"
```

---

## Task 8: SignalBadge Component

**Files:**
- Create: `src/frontend/src/features/ebay/components/SignalBadge.tsx`
- Create: `src/frontend/src/features/ebay/components/SignalBadge.module.css`
- Create: `src/frontend/src/features/ebay/components/__tests__/SignalBadge.test.tsx`

- [ ] **Step 1: Write the failing tests**

```typescript
// src/frontend/src/features/ebay/components/__tests__/SignalBadge.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { SignalBadge } from '../SignalBadge'
import type { ListingRecommendation } from '../../mockListings'

function makeRec(overrides: Partial<ListingRecommendation> = {}): ListingRecommendation {
  return {
    item_id: '111',
    suggested_action: 'hold',
    strategy_kind: 'balanced',
    suggested_price: null,
    confidence: 0.7,
    signals_used: 'behavioral',
    all_strategies: {},
    ...overrides,
  }
}

describe('SignalBadge', () => {
  it('shows loading skeleton when recommendation is undefined', () => {
    const { container } = render(<SignalBadge recommendation={undefined} />)
    expect(container.querySelector('[data-testid="signal-skeleton"]')).toBeTruthy()
  })

  it('renders raise badge with arrow and price when suggested_price is set', () => {
    const rec = makeRec({ suggested_action: 'raise', suggested_price: 15.50 })
    render(<SignalBadge recommendation={rec} />)
    expect(screen.getByText(/raise/i)).toBeTruthy()
    expect(screen.getByText(/\$15\.50/)).toBeTruthy()
  })

  it('renders lower badge', () => {
    render(<SignalBadge recommendation={makeRec({ suggested_action: 'lower', suggested_price: 8.00 })} />)
    expect(screen.getByText(/lower/i)).toBeTruthy()
  })

  it('renders hold badge with no price', () => {
    render(<SignalBadge recommendation={makeRec({ suggested_action: 'hold' })} />)
    expect(screen.getByText(/hold/i)).toBeTruthy()
  })

  it('renders draft badge', () => {
    render(<SignalBadge recommendation={makeRec({ suggested_action: 'draft' })} />)
    expect(screen.getByText(/draft/i)).toBeTruthy()
  })

  it('shows queued state when pendingAction is set', () => {
    const rec = makeRec({ suggested_action: 'lower' })
    render(<SignalBadge recommendation={rec} pendingAction={{ action_id: '1', action_type: 'lower', strategy_kind: 'quick', suggested_price: null, status: 'pending' }} />)
    expect(screen.getByText(/queued/i)).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/SignalBadge.test.tsx
```

Expected: `Cannot find module '../SignalBadge'`.

- [ ] **Step 3: Write the component**

```typescript
// src/frontend/src/features/ebay/components/SignalBadge.tsx
import type { ListingRecommendation, PendingAction } from '../mockListings'
import styles from './SignalBadge.module.css'

interface SignalBadgeProps {
  recommendation: ListingRecommendation | undefined
  pendingAction?: PendingAction
}

const ACTION_CONFIG = {
  raise:  { label: 'Raise', symbol: '↑', mod: styles.raise },
  lower:  { label: 'Lower', symbol: '↓', mod: styles.lower },
  hold:   { label: 'Hold',  symbol: '⏸', mod: styles.hold  },
  draft:  { label: 'Draft', symbol: '◻', mod: styles.draft  },
} as const

function formatUSD(value: number): string {
  return `$${value.toFixed(2)}`
}

export function SignalBadge({ recommendation, pendingAction }: SignalBadgeProps) {
  if (recommendation === undefined) {
    return <span data-testid="signal-skeleton" className={styles.skeleton} aria-label="Loading signal" />
  }

  if (pendingAction && ['pending', 'processing'].includes(pendingAction.status)) {
    return <span className={[styles.badge, styles.queued].join(' ')}>⏳ Queued</span>
  }

  const cfg = ACTION_CONFIG[recommendation.suggested_action]
  const price = recommendation.suggested_price !== null
    ? ` ${formatUSD(recommendation.suggested_price)}`
    : ''

  return (
    <span className={[styles.badge, cfg.mod].join(' ')}>
      {cfg.symbol} {cfg.label}{price}
    </span>
  )
}
```

- [ ] **Step 4: Write the CSS**

```css
/* src/frontend/src/features/ebay/components/SignalBadge.module.css */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
}

.raise  { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.lower  { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.hold   { background: rgba(148, 163, 184, 0.12); color: #94a3b8; }
.draft  { background: rgba(248, 113, 113, 0.15); color: #f87171; }
.queued { background: rgba(167, 139, 250, 0.15); color: #a78bfa; }

.skeleton {
  display: inline-block;
  width: 60px;
  height: 16px;
  border-radius: 4px;
  background: linear-gradient(90deg, #2a2a3a 25%, #33334a 50%, #2a2a3a 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/SignalBadge.test.tsx
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/SignalBadge.tsx \
        src/frontend/src/features/ebay/components/SignalBadge.module.css \
        src/frontend/src/features/ebay/components/__tests__/SignalBadge.test.tsx
git commit -m "feat(frontend): add SignalBadge component"
```

---

## Task 9: Listings Table Signal Column

**Files:**
- Modify: `src/frontend/src/features/ebay/components/ListingsTable.tsx`
- Modify: `src/frontend/src/routes/listings.tsx`

- [ ] **Step 1: Add Signal column to ListingsTable.tsx**

In `ListingsTable.tsx`:

1. Add the import at the top (after existing imports):
```typescript
import { SignalBadge } from './SignalBadge'
```

2. Change `COL_COUNT` from `10` to `11`:
```typescript
const COL_COUNT = 11
```

3. In the table `<thead>`, add the Signal header after the last `<th>` (before the closing `</tr>`):
```tsx
<th className={styles.th}>Signal</th>
```

4. In the table `<tbody>` row mapping, add the Signal cell after the last `<td>` (before the closing `</tr>`). It goes right after the watchers cell:
```tsx
<td className={styles.td}>
  <SignalBadge
    recommendation={listing.recommendation}
    pendingAction={listing.pendingAction}
  />
</td>
```

- [ ] **Step 2: Fetch recommendations after listings load in listings.tsx**

In `src/frontend/src/routes/listings.tsx`, add the following imports near the top:

```typescript
import { fetchRecommendation } from '../features/ebay/api'
```

Add this store selector near the other store selectors (around line 68):

```typescript
const storeSetRecommendation = useListingsStore((s) => s.setRecommendation)
```

After the `enrichWithCatalog` block inside the `load()` function (around line 141), add a recommendation fetch:

```typescript
// Fetch recommendations lazily — fire and forget, don't block the UI.
// Each rec updates both the store AND local listings state so the table re-renders.
;(async () => {
  for (const listing of listingsRef.current) {
    try {
      const rec = await fetchRecommendation(
        listing.itemId,
        listing.daysListed,
        listing.watchCount,
        listing.price,
        listing.currency,
      )
      if (!cancelled) {
        storeSetRecommendation(listing.itemId, rec)
        listingsRef.current = listingsRef.current.map((l) =>
          l.itemId === listing.itemId ? { ...l, recommendation: rec } : l
        )
        setListings([...listingsRef.current])
      }
    } catch {
      // Recommendation fetch failure is non-blocking
    }
  }
})()
```

- [ ] **Step 3: Verify the table renders with the new column**

Start the dev server and navigate to `/listings`:

```bash
cd src/frontend && npm run dev
```

Open `http://localhost:5173/listings`. After listings load, the Signal column should appear. Each row should show a loading skeleton briefly, then a badge (e.g. `⏸ Hold`, `↑ Raise`, `↓ Lower`).

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/ebay/components/ListingsTable.tsx \
        src/frontend/src/routes/listings.tsx
git commit -m "feat(frontend): add Signal column to listings table"
```

---

## Task 10: Detail Panel Strategy Advisor

**Files:**
- Modify: `src/frontend/src/features/ebay/components/ListingDetailPanel.tsx`

- [ ] **Step 1: Add strategy advisor to ListingDetailPanel.tsx**

Replace the full contents of `ListingDetailPanel.tsx`:

```typescript
// src/frontend/src/features/ebay/components/ListingDetailPanel.tsx
import { useState } from 'react'
import { Icon } from '../../../components/design-system/Icon'
import {
  StrategyCard,
  buildStrategies,
  type StrategyKind,
} from './StrategyCard'
import { SignalBadge } from './SignalBadge'
import { stageAction } from '../api'
import { useListingsStore } from '../../../store/listings'
import type { EbayLiveListing } from '../mockListings'
import styles from './ListingDetailPanel.module.css'

interface ListingDetailPanelProps {
  listing: EbayLiveListing
  onEdit: () => void
  onClose: () => void
  onCompare: () => void
}

const CONFIDENCE_LABEL = (c: number) =>
  c >= 0.85 ? 'High' : c >= 0.7 ? 'Medium' : 'Low'

const ACTION_TO_KIND: Record<string, StrategyKind> = {
  raise: 'max',
  lower: 'quick',
  hold: 'balanced',
  draft: 'balanced',
}

export function ListingDetailPanel({ listing, onEdit, onClose, onCompare }: ListingDetailPanelProps) {
  const rec = listing.recommendation
  const defaultKind: StrategyKind = rec
    ? (ACTION_TO_KIND[rec.suggested_action] ?? 'balanced')
    : 'balanced'
  const [selectedKind, setSelectedKind] = useState<StrategyKind>(defaultKind)
  const [isStaging, setIsStaging] = useState(false)
  const [stageError, setStageError] = useState<string | null>(null)
  const setPendingAction = useListingsStore((s) => s.setPendingAction)

  const strategies = buildStrategies(listing.price)

  async function handleStage() {
    const selected = strategies.find((s) => s.kind === selectedKind)
    if (!selected) return
    if (selectedKind === 'hold') return  // hold is not stageable from UI

    const midPct = (selected.pctRange[0] + selected.pctRange[1]) / 2
    const suggestedPrice = rec?.suggested_price ?? listing.price * (1 + midPct / 100)

    const actionType = selectedKind === 'quick' ? 'lower'
      : selectedKind === 'max' ? 'raise'
      : selectedKind === 'auctionReserve' || selectedKind === 'auction7' ? 'raise'
      : 'hold'

    if (actionType === 'hold') return

    setIsStaging(true)
    setStageError(null)
    try {
      const action = await stageAction(listing.itemId, {
        app_code: listing.appCode,
        action_type: actionType as 'raise' | 'lower' | 'draft',
        strategy_kind: selectedKind,
        suggested_price: suggestedPrice,
      })
      setPendingAction(listing.itemId, action)
    } catch (err) {
      setStageError(err instanceof Error ? err.message : 'Failed to stage action')
    } finally {
      setIsStaging(false)
    }
  }

  const hasPending = listing.pendingAction &&
    ['pending', 'processing'].includes(listing.pendingAction.status)

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>{listing.cardName}</span>
        <button onClick={onClose} className={styles.closeBtn} aria-label="Close panel">
          <Icon kind="close" size={14} color="currentColor" />
        </button>
      </div>

      {listing.imageUrl ? (
        <img src={listing.imageUrl} alt={listing.cardName} className={styles.image} />
      ) : (
        <div className={styles.imagePlaceholder}>
          <span className={styles.placeholderSet}>{listing.setCode}</span>
        </div>
      )}

      <div className={styles.fields}>
        {[
          { label: 'Set', value: listing.setCode || '—' },
          { label: 'Condition', value: listing.conditionLabel || '—' },
          { label: 'Days listed', value: listing.daysListed > 0 ? `${listing.daysListed}d` : '—' },
          { label: 'App', value: listing.appName || listing.appCode },
        ].map(({ label, value }) => (
          <div key={label} className={styles.row}>
            <span className={styles.label}>{label}</span>
            <span className={styles.value}>{value}</span>
          </div>
        ))}
        <div className={styles.row}>
          <span className={styles.label}>Price</span>
          <span className={styles.valueAccent}>
            {listing.currency} {listing.price.toFixed(2)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>Watchers</span>
          <span className={styles.value}>{listing.watchCount}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>eBay</span>
          <a
            href={listing.viewItemUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.link}
          >
            View ↗
          </a>
        </div>
      </div>

      {/* ── Strategy advisor ──────────────────────────────── */}
      <div className={styles.advisorSection}>
        <div className={styles.advisorHeader}>
          <span className={styles.advisorTitle}>Strategy advisor</span>
          {rec && (
            <span className={styles.advisorMeta}>
              <SignalBadge recommendation={rec} pendingAction={listing.pendingAction} />
              {' '}
              <span className={styles.confidence}>
                {CONFIDENCE_LABEL(rec.confidence)} confidence
              </span>
              {' · '}
              <span className={styles.signalSource}>
                {rec.signals_used === 'market' ? 'Market data' : 'Activity signals'}
              </span>
            </span>
          )}
        </div>

        <div className={styles.strategyList}>
          {strategies.map((s) => (
            <StrategyCard
              key={s.kind}
              strategy={s}
              selected={selectedKind === s.kind}
              onSelect={setSelectedKind}
            />
          ))}
        </div>

        {hasPending ? (
          <div className={styles.pendingBanner}>
            ⏳ Action queued — waiting for sync
            ({listing.pendingAction!.action_type} · {listing.pendingAction!.strategy_kind})
          </div>
        ) : (
          <>
            {selectedKind !== 'hold' && (
              <button
                className={styles.stageBtn}
                onClick={handleStage}
                disabled={isStaging}
              >
                {isStaging ? 'Staging…' : 'Stage action'}
              </button>
            )}
            {stageError && <p className={styles.stageError}>{stageError}</p>}
          </>
        )}
      </div>

      <div className={styles.actions}>
        <button onClick={onCompare} className={styles.compareBtn}>Compare market</button>
        <button onClick={onEdit} className={styles.editBtn}>Edit listing</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add CSS for advisor section to ListingDetailPanel.module.css**

Append to `src/frontend/src/features/ebay/components/ListingDetailPanel.module.css`:

```css
/* Strategy advisor */
.advisorSection {
  margin-top: 16px;
  border-top: 1px solid var(--hd-border, #1e2030);
  padding-top: 12px;
}

.advisorHeader {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.advisorTitle {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hd-sub, #64748b);
}

.advisorMeta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.confidence, .signalSource {
  font-size: 11px;
  color: var(--hd-sub, #64748b);
}

.strategyList {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stageBtn {
  margin-top: 10px;
  width: 100%;
  padding: 8px 0;
  background: var(--hd-accent, #7c3aed);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.stageBtn:disabled { opacity: 0.5; cursor: not-allowed; }
.stageBtn:hover:not(:disabled) { opacity: 0.85; }

.pendingBanner {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(167, 139, 250, 0.1);
  color: #a78bfa;
  font-size: 12px;
}

.stageError {
  margin-top: 6px;
  font-size: 11px;
  color: #f87171;
}
```

- [ ] **Step 3: Test the full flow in the browser**

```bash
cd src/frontend && npm run dev
```

1. Navigate to `/listings`
2. Wait for listings + Signal badges to load
3. Click a row — detail panel opens
4. Scroll to "Strategy advisor" section — 5 strategy cards visible
5. Select "Quick sale" (or any non-Hold strategy)
6. Click "Stage action"
7. Badge in panel should change to "⏳ Queued"
8. Signal column badge for that row should also show "⏳ Queued"

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/ebay/components/ListingDetailPanel.tsx \
        src/frontend/src/features/ebay/components/ListingDetailPanel.module.css
git commit -m "feat(frontend): add strategy advisor to ListingDetailPanel with stage action"
```

---

## Self-Review Checklist

Run after completing all tasks before opening a PR:

```bash
# Backend tests
cd src/automana && python -m pytest tests/unit/services/ebay/test_listing_recommendation_service.py \
  tests/unit/repositories/ebay/test_listing_actions_repository.py -v

# Frontend tests
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/SignalBadge.test.tsx

# TypeScript
cd src/frontend && npx tsc --noEmit

# Import smoke test
cd src && python -c "
from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
from automana.core.repositories.app_integration.ebay.listing_actions_repository import EbayListingActionsRepository
from automana.core.services.app_integration.ebay.listing_actions_service import stage_action
from automana.worker.tasks.ebay_actions import drain_listing_actions
print('All imports OK')
"
```

Expected: 13 backend tests passed, 6 frontend tests passed, 0 TypeScript errors, "All imports OK".
