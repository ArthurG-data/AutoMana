# eBay Sold Price Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist eBay sold prices from two channels (own Fulfillment API orders + external Finding API scrape) into `pricing.price_observation` via nightly Celery jobs.

**Architecture:** New tables `ebay_active_listings` and `ebay_scraped_sold` act as staging layers. `EbaySalesRepository` and `EbayScrapeSoldRepository` handle all DB writes. Three nightly services: `sync_own_sales`, `scrape_external_sold`, and `promote_sold_obs`. A shared `ensure_source_product()` helper creates the pricing chain (`mtg_card_products → product_ref → source_product`) on demand.

**Tech Stack:** Python 3.11, asyncpg, Pydantic v2, FastAPI, Celery 5, PostgreSQL 17, TimescaleDB.

**Spec:** `docs/superpowers/specs/2026-05-13-ebay-sold-price-persistence-design.md`

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Create | `src/automana/database/SQL/migrations/migration_31_ebay_listings_scrape.sql` | Both new tables + grants |
| Create | `src/automana/core/repositories/app_integration/ebay/sales_queries.py` | SQL strings for sales repo |
| Create | `src/automana/core/repositories/app_integration/ebay/sales_repository.py` | `EbaySalesRepository` |
| Create | `src/automana/core/repositories/pricing/ebay_scrape_queries.py` | SQL strings for scrape repo |
| Create | `src/automana/core/repositories/pricing/ebay_scrape_repository.py` | `EbayScrapeSoldRepository` |
| Modify | `src/automana/core/repositories/app_integration/ebay/auth_repository.py` | Add `get_active_app_code_users()` |
| Modify | `src/automana/core/service_registry.py` | Register `ebay_sales` + `ebay_scrape` repos |
| Create | `src/automana/core/services/app_integration/ebay/sales_sync_service.py` | `sync_own_sales` service |
| Create | `src/automana/core/services/app_integration/ebay/scrape_sold_service.py` | `scrape_external_sold` service |
| Create | `src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py` | `promote_sold_obs` service |
| Modify | `src/automana/core/service_modules.py` | Register 3 new service modules |
| Modify | `src/automana/api/routers/integrations/ebay/ebay_selling.py` | Write to `ebay_active_listings` after listing creation |
| Modify | `src/automana/worker/tasks/ebay.py` | Add 2 new Celery task functions |
| Modify | `src/automana/worker/celeryconfig.py` | Add 3 nightly beat entries |

---

## Task 1: DB Migration

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_31_ebay_listings_scrape.sql`

- [ ] **Step 1.1 — Write the migration**

```sql
-- migration_31_ebay_listings_scrape.sql
BEGIN;

-- Track which card_version was listed for each eBay item_id.
-- Written by POST /listing/from-card; read by sync_own_sales to skip title resolution.
CREATE TABLE IF NOT EXISTS app_integration.ebay_active_listings (
    item_id         TEXT         PRIMARY KEY,
    app_code        VARCHAR(50)  NOT NULL
        REFERENCES app_integration.app_info(app_code) ON DELETE CASCADE,
    card_version_id UUID         NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    listed_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ebay_active_listings_app
    ON app_integration.ebay_active_listings (app_code);
CREATE INDEX IF NOT EXISTS idx_ebay_active_listings_card
    ON app_integration.ebay_active_listings (card_version_id);

GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_active_listings
    TO app_backend, app_celery;

-- Staging for external Finding API scrape results.
-- One row per scraped sold listing; deduplicates on item_id.
CREATE TABLE IF NOT EXISTS pricing.ebay_scraped_sold (
    scrape_id         BIGSERIAL    PRIMARY KEY,
    item_id           TEXT         NOT NULL UNIQUE,
    title             TEXT         NOT NULL,
    source_product_id BIGINT       REFERENCES pricing.source_product(source_product_id),
    price_cents       INTEGER      NOT NULL CHECK (price_cents >= 0),
    currency          VARCHAR(3)   NOT NULL DEFAULT 'USD',
    condition_id      SMALLINT     REFERENCES pricing.card_condition(condition_id),
    finish_id         SMALLINT     NOT NULL DEFAULT pricing.default_finish_id(),
    language_id       SMALLINT     NOT NULL DEFAULT card_catalog.default_language_id(),
    sold_at           TIMESTAMPTZ  NOT NULL,
    scraped_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    promoted_to_obs   BOOLEAN      NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_ebay_scraped_unpromoted
    ON pricing.ebay_scraped_sold (source_product_id)
    WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ebay_scraped_sold_at
    ON pricing.ebay_scraped_sold (sold_at DESC);

GRANT SELECT, INSERT, UPDATE ON pricing.ebay_scraped_sold
    TO app_backend, app_celery;
GRANT USAGE ON SEQUENCE pricing.ebay_scraped_sold_scrape_id_seq
    TO app_backend, app_celery;

COMMIT;
```

- [ ] **Step 1.2 — Apply the migration**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
  < src/automana/database/SQL/migrations/migration_31_ebay_listings_scrape.sql
```

Expected output:
```
BEGIN
CREATE TABLE
CREATE INDEX
CREATE INDEX
GRANT
CREATE TABLE
CREATE INDEX
CREATE INDEX
GRANT
GRANT
COMMIT
```

- [ ] **Step 1.3 — Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d app_integration.ebay_active_listings" \
  -c "\d pricing.ebay_scraped_sold"
```

Expected: both tables with columns as specified above.

- [ ] **Step 1.4 — Commit**

```bash
git add src/automana/database/SQL/migrations/migration_31_ebay_listings_scrape.sql
git commit -m "feat(ebay): migration_31 — add ebay_active_listings and ebay_scraped_sold tables"
```

---

## Task 2: EbaySalesRepository

**Files:**
- Create: `src/automana/core/repositories/app_integration/ebay/sales_queries.py`
- Create: `src/automana/core/repositories/app_integration/ebay/sales_repository.py`
- Create: `tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py`

- [ ] **Step 2.1 — Write failing tests**

```python
# tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository


def make_repo():
    conn = MagicMock()
    repo = EbaySalesRepository.__new__(EbaySalesRepository)
    repo.connection = conn
    repo.executor = None
    return repo


@pytest.mark.asyncio
async def test_upsert_active_listing_calls_execute_command(monkeypatch):
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)
    item_id = "111222333"
    card_version_id = uuid4()
    await repo.upsert_active_listing(item_id, "automana_au", card_version_id)
    repo.execute_command.assert_called_once()
    args = repo.execute_command.call_args[0]
    assert item_id in args[1]
    assert str(card_version_id) in str(args[1])


@pytest.mark.asyncio
async def test_get_card_version_by_item_returns_uuid(monkeypatch):
    repo = make_repo()
    uid = uuid4()
    repo.execute_query = AsyncMock(return_value=[{"card_version_id": uid}])
    result = await repo.get_card_version_by_item("111")
    assert result == uid


@pytest.mark.asyncio
async def test_get_card_version_by_item_returns_none_when_not_found(monkeypatch):
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_card_version_by_item("999")
    assert result is None


@pytest.mark.asyncio
async def test_get_listed_card_versions_returns_list(monkeypatch):
    repo = make_repo()
    uid1, uid2 = uuid4(), uuid4()
    repo.execute_query = AsyncMock(return_value=[
        {"card_version_id": uid1}, {"card_version_id": uid2}
    ])
    result = await repo.get_listed_card_versions("automana_au")
    assert uid1 in result and uid2 in result


@pytest.mark.asyncio
async def test_ensure_source_product_returns_id(monkeypatch):
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[{"source_product_id": 42}])
    result = await repo.ensure_source_product(uuid4(), source_id=5)
    assert result == 42


@pytest.mark.asyncio
async def test_upsert_order_source_product_calls_command(monkeypatch):
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)
    await repo.upsert_order_source_product(
        order_id="ord-1",
        app_code="automana_au",
        item_id="itm-1",
        title="Sheoldred DMR NM",
        source_product_id=42,
        quantity=1,
        sold_price_cents=4500,
        currency="USD",
        finish_id=1,
        condition_id=1,
        language_id=1,
        sold_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        buyer_username="buyer123",
    )
    repo.execute_command.assert_called_once()


@pytest.mark.asyncio
async def test_get_unpromoted_own_returns_rows(monkeypatch):
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[
        {"ebay_osp_id": 1, "source_product_id": 42, "sold_price_cents": 4500,
         "finish_id": 1, "condition_id": 1, "language_id": 1,
         "sold_at": datetime(2026, 5, 1, tzinfo=timezone.utc)}
    ])
    rows = await repo.get_unpromoted_own()
    assert len(rows) == 1
    assert rows[0]["ebay_osp_id"] == 1


@pytest.mark.asyncio
async def test_mark_own_promoted_calls_command(monkeypatch):
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)
    await repo.mark_own_promoted([1, 2, 3])
    repo.execute_command.assert_called_once()
```

- [ ] **Step 2.2 — Run tests, expect ImportError**

```bash
cd /home/arthur/projects/AutoMana
.venv/bin/pytest tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError: No module named 'automana.core.repositories.app_integration.ebay.sales_repository'`

- [ ] **Step 2.3 — Create sales_queries.py**

```python
# src/automana/core/repositories/app_integration/ebay/sales_queries.py

upsert_active_listing = """
INSERT INTO app_integration.ebay_active_listings
    (item_id, app_code, card_version_id, listed_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (item_id) DO UPDATE SET
    ended_at   = NULL,
    updated_at = now()
"""

get_card_version_by_item = """
SELECT card_version_id
FROM app_integration.ebay_active_listings
WHERE item_id = $1
"""

get_listed_card_versions = """
SELECT DISTINCT card_version_id
FROM app_integration.ebay_active_listings
WHERE app_code = $1
  AND ended_at IS NULL
"""

ensure_source_product = """
WITH ins AS (
    INSERT INTO pricing.source_product (product_id, source_id)
    SELECT product_id, $2
    FROM pricing.mtg_card_products
    WHERE card_version_id = $1
    ON CONFLICT (product_id, source_id) DO NOTHING
    RETURNING source_product_id
)
SELECT source_product_id FROM ins
UNION ALL
SELECT sp.source_product_id
FROM pricing.source_product sp
JOIN pricing.mtg_card_products mcp ON mcp.product_id = sp.product_id
WHERE mcp.card_version_id = $1
  AND sp.source_id = $2
LIMIT 1
"""

upsert_order_source_product = """
INSERT INTO app_integration.ebay_order_source_product
    (order_id, app_code, item_id, title, source_product_id, quantity,
     sold_price_cents, currency, finish_id, condition_id, language_id,
     sold_at, buyer_username, promoted_to_obs)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, false)
ON CONFLICT (order_id, app_code, item_id) DO UPDATE SET
    source_product_id = COALESCE(EXCLUDED.source_product_id,
                                 app_integration.ebay_order_source_product.source_product_id),
    sold_price_cents  = EXCLUDED.sold_price_cents,
    updated_at        = now()
"""

get_unpromoted_own = """
SELECT ebay_osp_id, source_product_id, sold_price_cents,
       finish_id, condition_id, language_id, sold_at
FROM app_integration.ebay_order_source_product
WHERE promoted_to_obs = false
  AND source_product_id IS NOT NULL
ORDER BY sold_at
"""

mark_own_promoted = """
UPDATE app_integration.ebay_order_source_product
SET promoted_to_obs = true,
    updated_at      = now()
WHERE ebay_osp_id = ANY($1::BIGINT[])
"""
```

- [ ] **Step 2.4 — Create sales_repository.py**

```python
# src/automana/core/repositories/app_integration/ebay/sales_repository.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.repositories.app_integration.ebay import sales_queries

logger = logging.getLogger(__name__)

_EBAY_SOURCE_ID = 5


class EbaySalesRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "EbaySalesRepository"

    async def upsert_active_listing(
        self,
        item_id: str,
        app_code: str,
        card_version_id: UUID,
    ) -> None:
        await self.execute_command(
            sales_queries.upsert_active_listing,
            (item_id, app_code, str(card_version_id)),
        )

    async def get_card_version_by_item(self, item_id: str) -> Optional[UUID]:
        rows = await self.execute_query(
            sales_queries.get_card_version_by_item, (item_id,)
        )
        if not rows:
            return None
        return rows[0]["card_version_id"]

    async def get_listed_card_versions(self, app_code: str) -> list[UUID]:
        rows = await self.execute_query(
            sales_queries.get_listed_card_versions, (app_code,)
        )
        return [row["card_version_id"] for row in (rows or [])]

    async def ensure_source_product(
        self, card_version_id: UUID, source_id: int = _EBAY_SOURCE_ID
    ) -> Optional[int]:
        rows = await self.execute_query(
            sales_queries.ensure_source_product,
            (str(card_version_id), source_id),
        )
        if not rows:
            logger.warning(
                "ensure_source_product_no_product_ref",
                extra={"card_version_id": str(card_version_id)},
            )
            return None
        return rows[0]["source_product_id"]

    async def upsert_order_source_product(
        self,
        order_id: str,
        app_code: str,
        item_id: str,
        title: str,
        source_product_id: Optional[int],
        quantity: int,
        sold_price_cents: int,
        currency: str,
        finish_id: int,
        condition_id: Optional[int],
        language_id: int,
        sold_at: datetime,
        buyer_username: Optional[str],
    ) -> None:
        await self.execute_command(
            sales_queries.upsert_order_source_product,
            (
                order_id, app_code, item_id, title, source_product_id,
                quantity, sold_price_cents, currency, finish_id,
                condition_id, language_id, sold_at, buyer_username,
            ),
        )

    async def get_unpromoted_own(self) -> list[dict]:
        rows = await self.execute_query(sales_queries.get_unpromoted_own, ())
        return [dict(r) for r in (rows or [])]

    async def mark_own_promoted(self, ebay_osp_ids: list[int]) -> None:
        if not ebay_osp_ids:
            return
        await self.execute_command(
            sales_queries.mark_own_promoted, (ebay_osp_ids,)
        )
```

- [ ] **Step 2.5 — Run tests, expect PASS**

```bash
.venv/bin/pytest tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py -v 2>&1 | tail -15
```

Expected: 8 passed.

- [ ] **Step 2.6 — Commit**

```bash
git add \
  src/automana/core/repositories/app_integration/ebay/sales_queries.py \
  src/automana/core/repositories/app_integration/ebay/sales_repository.py \
  tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py
git commit -m "feat(ebay): add EbaySalesRepository with active listings + ensure_source_product"
```

---

## Task 3: EbayScrapeSoldRepository

**Files:**
- Create: `src/automana/core/repositories/pricing/ebay_scrape_queries.py`
- Create: `src/automana/core/repositories/pricing/ebay_scrape_repository.py`
- Create: `tests/unit/core/repositories/pricing/test_ebay_scrape_repository.py`

- [ ] **Step 3.1 — Write failing tests**

```python
# tests/unit/core/repositories/pricing/test_ebay_scrape_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from automana.core.repositories.pricing.ebay_scrape_repository import EbayScrapeSoldRepository


def make_repo():
    repo = EbayScrapeSoldRepository.__new__(EbayScrapeSoldRepository)
    repo.connection = MagicMock()
    repo.executor = None
    return repo


@pytest.mark.asyncio
async def test_insert_scraped_sold_calls_command(monkeypatch):
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)
    await repo.insert_scraped_sold(
        item_id="abc123",
        title="Sheoldred DMR NM",
        source_product_id=42,
        price_cents=4500,
        currency="USD",
        condition_id=1,
        finish_id=1,
        language_id=1,
        sold_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    repo.execute_command.assert_called_once()


@pytest.mark.asyncio
async def test_get_unpromoted_returns_rows(monkeypatch):
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[
        {"scrape_id": 1, "source_product_id": 42, "price_cents": 4500,
         "finish_id": 1, "condition_id": 1, "language_id": 1,
         "sold_at": datetime(2026, 5, 1, tzinfo=timezone.utc)}
    ])
    rows = await repo.get_unpromoted()
    assert len(rows) == 1
    assert rows[0]["scrape_id"] == 1


@pytest.mark.asyncio
async def test_mark_promoted_calls_command(monkeypatch):
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)
    await repo.mark_promoted([1, 2, 3])
    repo.execute_command.assert_called_once()


@pytest.mark.asyncio
async def test_mark_promoted_noop_on_empty(monkeypatch):
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)
    await repo.mark_promoted([])
    repo.execute_command.assert_not_called()
```

- [ ] **Step 3.2 — Run tests, expect ImportError**

```bash
.venv/bin/pytest tests/unit/core/repositories/pricing/test_ebay_scrape_repository.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3.3 — Create ebay_scrape_queries.py**

```python
# src/automana/core/repositories/pricing/ebay_scrape_queries.py

insert_scraped_sold = """
INSERT INTO pricing.ebay_scraped_sold
    (item_id, title, source_product_id, price_cents, currency,
     condition_id, finish_id, language_id, sold_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (item_id) DO NOTHING
"""

get_unpromoted = """
SELECT scrape_id, source_product_id, price_cents,
       finish_id, condition_id, language_id, sold_at
FROM pricing.ebay_scraped_sold
WHERE promoted_to_obs = false
  AND source_product_id IS NOT NULL
ORDER BY sold_at
"""

mark_promoted = """
UPDATE pricing.ebay_scraped_sold
SET promoted_to_obs = true,
    scraped_at      = scraped_at
WHERE scrape_id = ANY($1::BIGINT[])
"""
```

- [ ] **Step 3.4 — Create ebay_scrape_repository.py**

```python
# src/automana/core/repositories/pricing/ebay_scrape_repository.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.repositories.pricing import ebay_scrape_queries

logger = logging.getLogger(__name__)


class EbayScrapeSoldRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "EbayScrapeSoldRepository"

    async def insert_scraped_sold(
        self,
        item_id: str,
        title: str,
        source_product_id: Optional[int],
        price_cents: int,
        currency: str,
        condition_id: Optional[int],
        finish_id: int,
        language_id: int,
        sold_at: datetime,
    ) -> None:
        await self.execute_command(
            ebay_scrape_queries.insert_scraped_sold,
            (item_id, title, source_product_id, price_cents, currency,
             condition_id, finish_id, language_id, sold_at),
        )

    async def get_unpromoted(self) -> list[dict]:
        rows = await self.execute_query(ebay_scrape_queries.get_unpromoted, ())
        return [dict(r) for r in (rows or [])]

    async def mark_promoted(self, scrape_ids: list[int]) -> None:
        if not scrape_ids:
            return
        await self.execute_command(
            ebay_scrape_queries.mark_promoted, (scrape_ids,)
        )
```

- [ ] **Step 3.5 — Run tests, expect PASS**

```bash
.venv/bin/pytest tests/unit/core/repositories/pricing/test_ebay_scrape_repository.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 3.6 — Commit**

```bash
git add \
  src/automana/core/repositories/pricing/ebay_scrape_queries.py \
  src/automana/core/repositories/pricing/ebay_scrape_repository.py \
  tests/unit/core/repositories/pricing/test_ebay_scrape_repository.py
git commit -m "feat(ebay): add EbayScrapeSoldRepository for Finding API staging"
```

---

## Task 4: Add get_active_app_code_users to Auth Repository

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/auth_repository.py`
- Create: `tests/unit/core/repositories/app_integration/ebay/test_auth_repo_active_users.py`

The nightly sync task needs to iterate all `(user_id, app_code)` pairs that have a non-expired refresh token. This method queries `ebay_refresh_tokens` joined with `app_info`.

- [ ] **Step 4.1 — Write failing test**

```python
# tests/unit/core/repositories/app_integration/ebay/test_auth_repo_active_users.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository


def make_repo():
    repo = EbayAuthRepository.__new__(EbayAuthRepository)
    repo.connection = MagicMock()
    repo.executor = None
    return repo


@pytest.mark.asyncio
async def test_get_active_app_code_users_returns_pairs(monkeypatch):
    repo = make_repo()
    uid = uuid4()
    repo.execute_query = AsyncMock(return_value=[
        {"user_id": uid, "app_code": "automana_au"}
    ])
    result = await repo.get_active_app_code_users()
    assert len(result) == 1
    assert result[0] == (uid, "automana_au")


@pytest.mark.asyncio
async def test_get_active_app_code_users_empty(monkeypatch):
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_active_app_code_users()
    assert result == []
```

- [ ] **Step 4.2 — Run test, expect ImportError or AttributeError**

```bash
.venv/bin/pytest tests/unit/core/repositories/app_integration/ebay/test_auth_repo_active_users.py -v 2>&1 | tail -5
```

Expected: `AttributeError: type object 'EbayAuthRepository' has no attribute 'get_active_app_code_users'`

- [ ] **Step 4.3 — Add method to auth_repository.py**

Open `src/automana/core/repositories/app_integration/ebay/auth_repository.py` and append this method to the `EbayAuthRepository` class:

```python
    async def get_active_app_code_users(self) -> list[tuple]:
        """Return (user_id, app_code) for all non-expired refresh tokens."""
        query = """
            SELECT rt.user_id, ai.app_code
            FROM app_integration.ebay_refresh_tokens rt
            JOIN app_integration.app_info ai ON ai.app_id = rt.app_id
            WHERE rt.expires_at > now()
        """
        rows = await self.execute_query(query, ())
        return [(row["user_id"], row["app_code"]) for row in (rows or [])]
```

- [ ] **Step 4.4 — Run test, expect PASS**

```bash
.venv/bin/pytest tests/unit/core/repositories/app_integration/ebay/test_auth_repo_active_users.py -v 2>&1 | tail -5
```

Expected: 2 passed.

- [ ] **Step 4.5 — Commit**

```bash
git add \
  src/automana/core/repositories/app_integration/ebay/auth_repository.py \
  tests/unit/core/repositories/app_integration/ebay/test_auth_repo_active_users.py
git commit -m "feat(ebay): add get_active_app_code_users to EbayAuthRepository"
```

---

## Task 5: Register Repositories in ServiceRegistry

**Files:**
- Modify: `src/automana/core/service_registry.py`

- [ ] **Step 5.1 — Add registrations**

In `src/automana/core/service_registry.py`, find the block starting with `# Integration repositories` (around the `"app"` registration) and add after it:

```python
ServiceRegistry.register_db_repository(
    "ebay_sales",
    "automana.core.repositories.app_integration.ebay.sales_repository",
    "EbaySalesRepository",
)
ServiceRegistry.register_db_repository(
    "ebay_scrape",
    "automana.core.repositories.pricing.ebay_scrape_repository",
    "EbayScrapeSoldRepository",
)
```

- [ ] **Step 5.2 — Verify registrations load**

```bash
.venv/bin/python -c "
from automana.core.service_registry import ServiceRegistry
print(ServiceRegistry.get_db_repository('ebay_sales'))
print(ServiceRegistry.get_db_repository('ebay_scrape'))
"
```

Expected: two tuples with module path + class name printed.

- [ ] **Step 5.3 — Commit**

```bash
git add src/automana/core/service_registry.py
git commit -m "feat(ebay): register ebay_sales and ebay_scrape DB repositories"
```

---

## Task 6: Router — Write ebay_active_listings on Listing Creation

**Files:**
- Modify: `src/automana/api/routers/integrations/ebay/ebay_selling.py`
- Create: `tests/unit/core/routers/ebay/test_listing_tracking.py`

The `build_and_create_listing` endpoint calls `execute_service("integrations.ebay.selling.listings.build_and_create", ...)` and gets back a dict. The Trading API `AddFixedPriceItem` XML response returns `ItemID` at the top level of the parsed dict. After a successful response, write to `ebay_active_listings` via a new `integrations.ebay.track_active_listing` service call.

- [ ] **Step 6.1 — Write failing test**

```python
# tests/unit/core/routers/ebay/test_listing_tracking.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Tests that the router calls track_active_listing when listing succeeds.
# We test the service call, not the full HTTP stack.


@pytest.mark.asyncio
async def test_track_active_listing_called_after_success():
    """Service manager should call track_active_listing when ItemID is present."""
    from automana.core.services.app_integration.ebay.sales_sync_service import track_active_listing

    sales_repo = MagicMock()
    sales_repo.upsert_active_listing = AsyncMock(return_value=None)

    await track_active_listing(
        ebay_sales_repository=sales_repo,
        item_id="444555666",
        app_code="automana_au",
        card_version_id=uuid4(),
    )
    sales_repo.upsert_active_listing.assert_called_once()


@pytest.mark.asyncio
async def test_track_active_listing_skips_when_no_item_id():
    """No item_id → no DB write."""
    from automana.core.services.app_integration.ebay.sales_sync_service import track_active_listing

    sales_repo = MagicMock()
    sales_repo.upsert_active_listing = AsyncMock(return_value=None)

    await track_active_listing(
        ebay_sales_repository=sales_repo,
        item_id=None,
        app_code="automana_au",
        card_version_id=uuid4(),
    )
    sales_repo.upsert_active_listing.assert_not_called()
```

- [ ] **Step 6.2 — Run test, expect ImportError**

```bash
.venv/bin/pytest tests/unit/core/routers/ebay/test_listing_tracking.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError` — `sales_sync_service` does not exist yet. This test is intentionally written first so we verify the import works in Task 7.

- [ ] **Step 6.3 — Modify the router**

In `src/automana/api/routers/integrations/ebay/ebay_selling.py`, update `build_and_create_listing` to add the tracking call after the successful `execute_service` call:

Find this block (around line 83–100):

```python
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.build_and_create",
            user_id=user.unique_id,
            app_code=app_code,
            card_version_id=body.card_version_id,
            condition=body.condition,
            quantity=body.quantity,
            price_aud=body.price_aud,
            foil=body.foil,
            lang=body.lang,
            shipping_cost_aud=body.shipping_cost_aud,
            condition_note=body.condition_note,
            description_mode=body.description_mode,
            brand_config=body.brand_config,
            marketplace_id=body.marketplace_id,
            idempotency_key=idempotency_key,
        )
        return ApiResponse(data=result, message="Listing created successfully")
```

Replace with:

```python
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.build_and_create",
            user_id=user.unique_id,
            app_code=app_code,
            card_version_id=body.card_version_id,
            condition=body.condition,
            quantity=body.quantity,
            price_aud=body.price_aud,
            foil=body.foil,
            lang=body.lang,
            shipping_cost_aud=body.shipping_cost_aud,
            condition_note=body.condition_note,
            description_mode=body.description_mode,
            brand_config=body.brand_config,
            marketplace_id=body.marketplace_id,
            idempotency_key=idempotency_key,
        )
        item_id = result.get("ItemID") if isinstance(result, dict) else None
        if item_id:
            try:
                await service_manager.execute_service(
                    "integrations.ebay.track_active_listing",
                    item_id=item_id,
                    app_code=app_code,
                    card_version_id=body.card_version_id,
                )
            except Exception as exc:
                logger.warning(
                    "ebay_track_active_listing_failed",
                    extra={"item_id": item_id, "error": str(exc)},
                )
        return ApiResponse(data=result, message="Listing created successfully")
```

- [ ] **Step 6.4 — Commit router change**

```bash
git add src/automana/api/routers/integrations/ebay/ebay_selling.py
git commit -m "feat(ebay): write ebay_active_listings after listing creation (best-effort)"
```

---

## Task 7: sales_sync_service.py — Own Sales Sync + Listing Tracker

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/sales_sync_service.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_sales_sync_service.py`

This file contains two registered services:
- `integrations.ebay.track_active_listing` — written by the router after listing creation
- `integrations.ebay.sync_own_sales` — nightly sync of Fulfillment API order history

eBay condition display names (from Finding API / Fulfillment API) map to AutoMana `condition_id`:

| eBay string | condition_id |
|---|---|
| `New`, `Brand New`, `Like New` | 1 (NM) |
| `Very Good` | 2 (LP) |
| `Good` | 3 (MP) |
| `Acceptable` | 4 (HP) |
| `For parts or not working` | 5 (DMG) |

- [ ] **Step 7.1 — Write failing tests**

```python
# tests/unit/core/services/app_integration/ebay/test_sales_sync_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from automana.core.services.app_integration.ebay.sales_sync_service import (
    track_active_listing,
    _map_condition,
)


# ── track_active_listing ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_upserts_when_item_id_present():
    repo = MagicMock()
    repo.upsert_active_listing = AsyncMock()
    await track_active_listing(
        ebay_sales_repository=repo,
        item_id="777",
        app_code="automana_au",
        card_version_id=uuid4(),
    )
    repo.upsert_active_listing.assert_called_once()


@pytest.mark.asyncio
async def test_track_noop_when_item_id_none():
    repo = MagicMock()
    repo.upsert_active_listing = AsyncMock()
    await track_active_listing(
        ebay_sales_repository=repo,
        item_id=None,
        app_code="automana_au",
        card_version_id=uuid4(),
    )
    repo.upsert_active_listing.assert_not_called()


# ── _map_condition ──────────────────────────────────────────────────────────

def test_map_condition_new_is_nm():
    assert _map_condition("New") == 1

def test_map_condition_very_good_is_lp():
    assert _map_condition("Very Good") == 2

def test_map_condition_good_is_mp():
    assert _map_condition("Good") == 3

def test_map_condition_acceptable_is_hp():
    assert _map_condition("Acceptable") == 4

def test_map_condition_parts_is_dmg():
    assert _map_condition("For parts or not working") == 5

def test_map_condition_unknown_returns_none():
    assert _map_condition("mystery grade") is None

def test_map_condition_case_insensitive():
    assert _map_condition("very good") == 2
```

- [ ] **Step 7.2 — Run tests, expect ImportError**

```bash
.venv/bin/pytest tests/unit/core/services/app_integration/ebay/test_sales_sync_service.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 7.3 — Create sales_sync_service.py**

```python
# src/automana/core/services/app_integration/ebay/sales_sync_service.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository
from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository
from automana.core.repositories.card_catalog.card_repository import CardRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token
from automana.core.services.app_integration.ebay.market_price_scorer import score_title

logger = logging.getLogger(__name__)

_EBAY_SOURCE_ID = 5
_SCORE_THRESHOLD = 0.7

_CONDITION_MAP: dict[str, int] = {
    "new": 1,
    "brand new": 1,
    "like new": 1,
    "very good": 2,
    "good": 3,
    "acceptable": 4,
    "for parts or not working": 5,
}


def _map_condition(ebay_condition: str) -> Optional[int]:
    return _CONDITION_MAP.get(ebay_condition.lower())


@ServiceRegistry.register(
    path="integrations.ebay.track_active_listing",
    db_repositories=["ebay_sales"],
    runs_in_transaction=False,
)
async def track_active_listing(
    ebay_sales_repository: EbaySalesRepository,
    item_id: Optional[str],
    app_code: str,
    card_version_id: UUID,
    **kwargs: Any,
) -> None:
    if not item_id:
        logger.info("track_active_listing_skipped_no_item_id", extra={"app_code": app_code})
        return
    await ebay_sales_repository.upsert_active_listing(item_id, app_code, card_version_id)
    logger.info(
        "ebay_active_listing_tracked",
        extra={"item_id": item_id, "app_code": app_code},
    )


@ServiceRegistry.register(
    path="integrations.ebay.sync_own_sales",
    db_repositories=["auth", "app", "ebay_sales", "card"],
    api_repositories=["selling"],
    runs_in_transaction=False,
)
async def sync_own_sales(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    ebay_sales_repository: EbaySalesRepository,
    card_repository: CardRepository,
    selling_repository: EbaySellingRepository,
    days_back: int = 90,
    **kwargs: Any,
) -> dict:
    pairs = await auth_repository.get_active_app_code_users()
    if not pairs:
        logger.info("sync_own_sales_no_active_tokens")
        return {"synced_app_codes": 0, "total_orders": 0}

    total_orders = 0
    for user_id, app_code in pairs:
        try:
            synced = await _sync_for_app_code(
                auth_repository, app_repository, ebay_sales_repository,
                card_repository, selling_repository,
                user_id=user_id, app_code=app_code, days_back=days_back,
            )
            total_orders += synced
        except Exception as exc:
            logger.warning(
                "sync_own_sales_app_code_failed",
                extra={"app_code": app_code, "error": str(exc)},
            )

    return {"synced_app_codes": len(pairs), "total_orders": total_orders}


async def _sync_for_app_code(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    ebay_sales_repository: EbaySalesRepository,
    card_repository: CardRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    days_back: int,
) -> int:
    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    env = await auth_repository.get_environment(app_code=app_code)
    if env:
        selling_repository.environment = env.lower()

    raw = await selling_repository.get_history({"token": token, "limit": 200, "offset": 0})
    orders = raw.get("orders") or []
    synced = 0

    for order in orders:
        if not isinstance(order, dict):
            continue
        order_id = order.get("orderId")
        if not order_id:
            continue

        await app_repository.upsert_order_status(
            order_id=order_id,
            app_code=app_code,
            local_status="sold",
        )

        for line in order.get("lineItems") or []:
            await _process_line_item(
                ebay_sales_repository, card_repository,
                order_id=order_id, app_code=app_code,
                line=line, order=order,
            )
            synced += 1

    logger.info(
        "sync_own_sales_app_code_done",
        extra={"app_code": app_code, "orders": len(orders), "line_items": synced},
    )
    return synced


async def _process_line_item(
    ebay_sales_repository: EbaySalesRepository,
    card_repository: CardRepository,
    order_id: str,
    app_code: str,
    line: dict,
    order: dict,
) -> None:
    item_id = line.get("legacyItemId") or line.get("lineItemId", "")
    title = line.get("title", "")
    quantity = int(line.get("quantity", 1))
    price_info = line.get("lineItemCost") or {}
    price_str = price_info.get("value", "0")
    currency = price_info.get("currency", "USD")
    try:
        sold_price_cents = int(float(price_str) * 100)
    except (TypeError, ValueError):
        sold_price_cents = 0

    sold_at_str = order.get("creationDate", "")
    try:
        sold_at = datetime.fromisoformat(sold_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        sold_at = datetime.now(timezone.utc)

    buyer_username = order.get("buyer", {}).get("username")

    # Resolution: active listing lookup → title fallback
    card_version_id = await ebay_sales_repository.get_card_version_by_item(str(item_id))

    if card_version_id is None and title:
        suggestions = await card_repository.suggest(title, limit=3)
        for suggestion in suggestions:
            if score_title(title, suggestion.get("card_name", ""), None, None, None) >= _SCORE_THRESHOLD:
                card_version_id = suggestion.get("card_version_id")
                break

    source_product_id = None
    if card_version_id:
        source_product_id = await ebay_sales_repository.ensure_source_product(
            card_version_id, source_id=_EBAY_SOURCE_ID
        )

    await ebay_sales_repository.upsert_order_source_product(
        order_id=order_id,
        app_code=app_code,
        item_id=str(item_id),
        title=title,
        source_product_id=source_product_id,
        quantity=quantity,
        sold_price_cents=sold_price_cents,
        currency=currency,
        finish_id=1,
        condition_id=None,
        language_id=1,
        sold_at=sold_at,
        buyer_username=buyer_username,
    )
```

- [ ] **Step 7.4 — Run tests, expect PASS**

```bash
.venv/bin/pytest tests/unit/core/services/app_integration/ebay/test_sales_sync_service.py -v 2>&1 | tail -15
```

Expected: 9 passed.

- [ ] **Step 7.5 — Re-run router test from Task 6 — expect PASS now**

```bash
.venv/bin/pytest tests/unit/core/routers/ebay/test_listing_tracking.py -v 2>&1 | tail -10
```

Expected: 2 passed.

- [ ] **Step 7.6 — Commit**

```bash
git add \
  src/automana/core/services/app_integration/ebay/sales_sync_service.py \
  tests/unit/core/services/app_integration/ebay/test_sales_sync_service.py
git commit -m "feat(ebay): add track_active_listing + sync_own_sales services"
```

---

## Task 8: scrape_sold_service.py — External Finding API Scrape

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/scrape_sold_service.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_scrape_sold_service.py`

- [ ] **Step 8.1 — Write failing tests**

```python
# tests/unit/core/services/app_integration/ebay/test_scrape_sold_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from automana.core.services.app_integration.ebay.scrape_sold_service import (
    _parse_price_cents,
    _parse_sold_at,
    _resolve_condition_id,
)


def test_parse_price_cents_normal():
    assert _parse_price_cents(45.0, "USD") == 4500


def test_parse_price_cents_aud():
    assert _parse_price_cents(45.0, "AUD") == 4500


def test_parse_price_cents_zero_on_invalid():
    assert _parse_price_cents(-1.0, "USD") == 0


def test_parse_sold_at_valid_iso():
    dt = _parse_sold_at("2026-01-01T10:00:00.000Z")
    assert dt.year == 2026


def test_parse_sold_at_invalid_returns_now():
    dt = _parse_sold_at("not-a-date")
    assert (datetime.now(timezone.utc) - dt).total_seconds() < 5


def test_resolve_condition_id_very_good():
    assert _resolve_condition_id("Very Good") == 2


def test_resolve_condition_id_unknown():
    assert _resolve_condition_id("random") is None
```

- [ ] **Step 8.2 — Run tests, expect ImportError**

```bash
.venv/bin/pytest tests/unit/core/services/app_integration/ebay/test_scrape_sold_service.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 8.3 — Create scrape_sold_service.py**

```python
# src/automana/core/services/app_integration/ebay/scrape_sold_service.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository
from automana.core.repositories.pricing.ebay_scrape_repository import EbayScrapeSoldRepository
from automana.core.repositories.card_catalog.card_repository import CardRepository
from automana.core.repositories.app_integration.ebay.ApiFinding_repository import EbayFindingAPIRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)
from automana.core.settings import get_settings

logger = logging.getLogger(__name__)

_EBAY_SOURCE_ID = 5
_MTG_CATEGORY_ID = 2536
_SCORE_THRESHOLD = 0.7

_CONDITION_MAP: dict[str, int] = {
    "new": 1,
    "brand new": 1,
    "like new": 1,
    "very good": 2,
    "good": 3,
    "acceptable": 4,
    "for parts or not working": 5,
}


def _resolve_condition_id(ebay_condition: str) -> Optional[int]:
    return _CONDITION_MAP.get(ebay_condition.lower())


def _parse_price_cents(price: float, currency: str) -> int:
    if price < 0:
        return 0
    return int(price * 100)


def _parse_sold_at(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


@ServiceRegistry.register(
    path="integrations.ebay.scrape_external_sold",
    db_repositories=["auth", "ebay_sales", "ebay_scrape", "card"],
    api_repositories=["ebay_finding"],
    runs_in_transaction=False,
)
async def scrape_external_sold(
    auth_repository: EbayAuthRepository,
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    card_repository: CardRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    days_back: int = 30,
    score_threshold: float = _SCORE_THRESHOLD,
    limit_per_card: int = 50,
    **kwargs: Any,
) -> dict:
    settings = get_settings()
    app_id = settings.ebay_app_id or ""

    pairs = await auth_repository.get_active_app_code_users()
    if not pairs:
        return {"scraped_cards": 0, "inserted_rows": 0}

    # Collect distinct card_version_ids across all app_codes
    card_version_ids: set[UUID] = set()
    for _user_id, app_code in pairs:
        ids = await ebay_sales_repository.get_listed_card_versions(app_code)
        card_version_ids.update(ids)

    if not card_version_ids:
        logger.info("scrape_external_sold_no_listed_cards")
        return {"scraped_cards": 0, "inserted_rows": 0}

    inserted = 0
    for card_version_id in card_version_ids:
        try:
            n = await _scrape_card(
                card_repository=card_repository,
                ebay_sales_repository=ebay_sales_repository,
                ebay_scrape_repository=ebay_scrape_repository,
                ebay_finding_repository=ebay_finding_repository,
                card_version_id=card_version_id,
                app_id=app_id,
                days_back=days_back,
                score_threshold=score_threshold,
                limit_per_card=limit_per_card,
            )
            inserted += n
        except Exception as exc:
            logger.warning(
                "scrape_external_sold_card_failed",
                extra={"card_version_id": str(card_version_id), "error": str(exc)},
            )
        await asyncio.sleep(0.5)  # rate-limit: 2 cards/s

    return {"scraped_cards": len(card_version_ids), "inserted_rows": inserted}


async def _scrape_card(
    card_repository: CardRepository,
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    card_version_id: UUID,
    app_id: str,
    days_back: int,
    score_threshold: float,
    limit_per_card: int,
) -> int:
    card = await card_repository.get(card_version_id)
    if not card:
        return 0

    card_name = card.get("card_name", "")
    set_code = card.get("set_code")
    query = build_query_string(card_name, set_code, None, None)

    from datetime import timedelta
    min_date = datetime.now(timezone.utc) - timedelta(days=days_back)

    raw_items = await ebay_finding_repository.find_completed_items(
        keywords=query,
        app_id=app_id,
        category_id=_MTG_CATEGORY_ID,
        min_date=min_date,
        limit=limit_per_card,
    )

    source_product_id = await ebay_sales_repository.ensure_source_product(
        card_version_id, source_id=_EBAY_SOURCE_ID
    )

    inserted = 0
    for item in raw_items:
        title = item.get("title", "")
        if score_title(title, card_name, set_code, None, None) < score_threshold:
            continue

        condition_id = _resolve_condition_id(item.get("condition") or "")
        price_cents = _parse_price_cents(
            float(item.get("price", 0)), item.get("currency", "USD")
        )
        sold_at = _parse_sold_at(item.get("sold_date", ""))

        await ebay_scrape_repository.insert_scraped_sold(
            item_id=item.get("item_id", ""),
            title=title,
            source_product_id=source_product_id,
            price_cents=price_cents,
            currency=item.get("currency", "USD"),
            condition_id=condition_id,
            finish_id=1,
            language_id=1,
            sold_at=sold_at,
        )
        inserted += 1

    return inserted
```

- [ ] **Step 8.4 — Run tests, expect PASS**

```bash
.venv/bin/pytest tests/unit/core/services/app_integration/ebay/test_scrape_sold_service.py -v 2>&1 | tail -10
```

Expected: 7 passed.

- [ ] **Step 8.5 — Commit**

```bash
git add \
  src/automana/core/services/app_integration/ebay/scrape_sold_service.py \
  tests/unit/core/services/app_integration/ebay/test_scrape_sold_service.py
git commit -m "feat(ebay): add scrape_external_sold service (Finding API staging)"
```

---

## Task 9: promote_sold_obs_service.py — Nightly Promotion to price_observation

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_promote_sold_obs_service.py`

`price_observation` is a TimescaleDB hypertable. Inserts go through the child chunks — `INSERT ... ON CONFLICT` works normally. The PK is `(ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)`. We upsert `sold_avg_cents` and `sold_count` while leaving `list_*` columns alone.

Known values:
- `data_provider_id = 4` (ebay)
- `price_type_id = 1` (sell)
- `condition_id` defaults to `pricing.default_condition_id()` which returns `1` (NM)

- [ ] **Step 9.1 — Write failing tests**

```python
# tests/unit/core/services/app_integration/ebay/test_promote_sold_obs_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, datetime, timezone

from automana.core.services.app_integration.ebay.promote_sold_obs_service import (
    _group_rows,
    _rows_to_obs,
)


def _make_row(source_product_id, sold_at, price_cents, finish_id=1, condition_id=1, language_id=1):
    return {
        "source_product_id": source_product_id,
        "sold_at": sold_at,
        "sold_price_cents": price_cents,
        "price_cents": price_cents,
        "finish_id": finish_id,
        "condition_id": condition_id,
        "language_id": language_id,
    }


def test_group_rows_groups_by_key():
    dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows = [
        _make_row(42, dt, 4500),
        _make_row(42, dt, 5000),
        _make_row(99, dt, 3000),
    ]
    grouped = _group_rows(rows, price_key="sold_price_cents")
    assert len(grouped) == 2
    key = (42, date(2026, 5, 1), 1, 1, 1)
    assert len(grouped[key]) == 2


def test_rows_to_obs_computes_avg():
    dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows = [
        _make_row(42, dt, 4000),
        _make_row(42, dt, 5000),
    ]
    grouped = _group_rows(rows, price_key="sold_price_cents")
    obs = _rows_to_obs(grouped)
    assert len(obs) == 1
    assert obs[0]["sold_avg_cents"] == 4500
    assert obs[0]["sold_count"] == 2
    assert obs[0]["source_product_id"] == 42
    assert obs[0]["ts_date"] == date(2026, 5, 1)
    assert obs[0]["data_provider_id"] == 4
    assert obs[0]["price_type_id"] == 1


def test_rows_to_obs_single_row():
    dt = datetime(2026, 5, 3, tzinfo=timezone.utc)
    rows = [_make_row(7, dt, 3000)]
    grouped = _group_rows(rows, price_key="sold_price_cents")
    obs = _rows_to_obs(grouped)
    assert obs[0]["sold_avg_cents"] == 3000
    assert obs[0]["sold_count"] == 1
```

- [ ] **Step 9.2 — Run tests, expect ImportError**

```bash
.venv/bin/pytest tests/unit/core/services/app_integration/ebay/test_promote_sold_obs_service.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 9.3 — Create promote_sold_obs_service.py**

```python
# src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository
from automana.core.repositories.pricing.ebay_scrape_repository import EbayScrapeSoldRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

_DATA_PROVIDER_ID = 4   # ebay
_PRICE_TYPE_ID = 1       # sell
_BATCH_SIZE = 1000


def _group_rows(rows: list[dict], price_key: str) -> dict:
    groups: dict = defaultdict(list)
    for row in rows:
        sold_at = row["sold_at"]
        ts_date = sold_at.date() if isinstance(sold_at, datetime) else sold_at
        key = (
            row["source_product_id"],
            ts_date,
            row.get("finish_id", 1),
            row.get("condition_id") or 1,
            row.get("language_id", 1),
        )
        groups[key].append(row[price_key])
    return dict(groups)


def _rows_to_obs(grouped: dict) -> list[dict]:
    obs = []
    for (source_product_id, ts_date, finish_id, condition_id, language_id), prices in grouped.items():
        obs.append({
            "ts_date": ts_date,
            "source_product_id": source_product_id,
            "price_type_id": _PRICE_TYPE_ID,
            "finish_id": finish_id,
            "condition_id": condition_id,
            "language_id": language_id,
            "data_provider_id": _DATA_PROVIDER_ID,
            "sold_avg_cents": int(sum(prices) / len(prices)),
            "sold_count": len(prices),
        })
    return obs


_UPSERT_OBS = """
INSERT INTO pricing.price_observation
    (ts_date, source_product_id, price_type_id, finish_id, condition_id,
     language_id, data_provider_id, sold_avg_cents, sold_count, scraped_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
ON CONFLICT (ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)
DO UPDATE SET
    sold_avg_cents = EXCLUDED.sold_avg_cents,
    sold_count     = EXCLUDED.sold_count,
    updated_at     = now()
"""


@ServiceRegistry.register(
    path="integrations.ebay.promote_sold_obs",
    db_repositories=["ebay_sales", "ebay_scrape"],
    runs_in_transaction=False,
)
async def promote_sold_obs(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    **kwargs: Any,
) -> dict:
    own_rows = await ebay_sales_repository.get_unpromoted_own()
    scrape_rows = await ebay_scrape_repository.get_unpromoted()

    own_promoted = await _promote_batch(
        ebay_sales_repository.connection,
        own_rows,
        price_key="sold_price_cents",
        id_key="ebay_osp_id",
        mark_fn=ebay_sales_repository.mark_own_promoted,
    )
    scrape_promoted = await _promote_batch(
        ebay_scrape_repository.connection,
        scrape_rows,
        price_key="price_cents",
        id_key="scrape_id",
        mark_fn=ebay_scrape_repository.mark_promoted,
    )

    logger.info(
        "promote_sold_obs_done",
        extra={"own_promoted": own_promoted, "scrape_promoted": scrape_promoted},
    )
    return {"own_promoted": own_promoted, "scrape_promoted": scrape_promoted}


async def _promote_batch(
    connection,
    rows: list[dict],
    price_key: str,
    id_key: str,
    mark_fn,
) -> int:
    if not rows:
        return 0

    grouped = _group_rows(rows, price_key=price_key)
    obs_list = _rows_to_obs(grouped)

    promoted_count = 0
    for i in range(0, len(obs_list), _BATCH_SIZE):
        batch = obs_list[i : i + _BATCH_SIZE]
        async with connection.transaction():
            for obs in batch:
                await connection.execute(
                    _UPSERT_OBS,
                    obs["ts_date"],
                    obs["source_product_id"],
                    obs["price_type_id"],
                    obs["finish_id"],
                    obs["condition_id"],
                    obs["language_id"],
                    obs["data_provider_id"],
                    obs["sold_avg_cents"],
                    obs["sold_count"],
                )
            promoted_count += len(batch)

    # Mark as promoted — collect ids from original rows
    all_ids = [row[id_key] for row in rows]
    await mark_fn(all_ids)

    return promoted_count
```

- [ ] **Step 9.4 — Run tests, expect PASS**

```bash
.venv/bin/pytest tests/unit/core/services/app_integration/ebay/test_promote_sold_obs_service.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 9.5 — Commit**

```bash
git add \
  src/automana/core/services/app_integration/ebay/promote_sold_obs_service.py \
  tests/unit/core/services/app_integration/ebay/test_promote_sold_obs_service.py
git commit -m "feat(ebay): add promote_sold_obs service — both channels to price_observation"
```

---

## Task 10: Register Services in service_modules.py

**Files:**
- Modify: `src/automana/core/service_modules.py`

- [ ] **Step 10.1 — Add 3 new module paths**

In `src/automana/core/service_modules.py`, find the block containing `"automana.core.services.app_integration.ebay.fulfillment_service"` (appears in both `"backend"` and `"all"` lists). After `fulfillment_service` in each list, add:

```python
"automana.core.services.app_integration.ebay.sales_sync_service",
"automana.core.services.app_integration.ebay.scrape_sold_service",
"automana.core.services.app_integration.ebay.promote_sold_obs_service",
```

- [ ] **Step 10.2 — Verify all 3 services load**

```bash
.venv/bin/python -c "
import automana.core.service_modules  # triggers module loading
from automana.core.service_registry import ServiceRegistry
for path in [
    'integrations.ebay.track_active_listing',
    'integrations.ebay.sync_own_sales',
    'integrations.ebay.scrape_external_sold',
    'integrations.ebay.promote_sold_obs',
]:
    cfg = ServiceRegistry.get_service(path)
    print(f'{path}: db={cfg.db_repositories} api={cfg.api_repositories}')
" 2>&1
```

Expected: 4 lines, each showing the correct repo lists without errors.

- [ ] **Step 10.3 — Commit**

```bash
git add src/automana/core/service_modules.py
git commit -m "feat(ebay): register sales_sync, scrape_sold, promote_sold_obs in service_modules"
```

---

## Task 11: Celery Tasks + Beat Schedule

**Files:**
- Modify: `src/automana/worker/tasks/ebay.py`
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 11.1 — Add 2 dedicated task functions to ebay.py**

Replace the contents of `src/automana/worker/tasks/ebay.py` (the file is currently all commented-out legacy code) with:

```python
# src/automana/worker/tasks/ebay.py
import logging
from datetime import datetime

from celery import shared_task

from automana.worker.main import run_service
from automana.core.logging_context import set_task_id

logger = logging.getLogger(__name__)


@shared_task(name="automana.worker.tasks.ebay.ebay_sync_own_sales_task", bind=True)
def ebay_sync_own_sales_task(self):
    """Nightly: sync seller's eBay order history into ebay_order_source_product."""
    set_task_id(self.request.id)
    logger.info(
        "ebay_sync_own_sales_task_started",
        extra={"celery_task_id": self.request.id},
    )
    run_service.delay("integrations.ebay.sync_own_sales", days_back=90)


@shared_task(name="automana.worker.tasks.ebay.ebay_scrape_external_sold_task", bind=True)
def ebay_scrape_external_sold_task(self):
    """Nightly: scrape external eBay sold listings for listed cards."""
    set_task_id(self.request.id)
    logger.info(
        "ebay_scrape_external_sold_task_started",
        extra={"celery_task_id": self.request.id},
    )
    run_service.delay(
        "integrations.ebay.scrape_external_sold",
        days_back=30,
        score_threshold=0.7,
        limit_per_card=50,
    )
```

- [ ] **Step 11.2 — Add 3 beat entries to celeryconfig.py**

In `src/automana/worker/celeryconfig.py`, find the `beat_schedule = {` block and add before the closing `}`:

```python
    "ebay-sync-own-sales-nightly": {
        "task": "automana.worker.tasks.ebay.ebay_sync_own_sales_task",
        "schedule": crontab(hour=7, minute=0),   # 07:00 AEST — after daily pipelines
    },
    "ebay-scrape-external-sold-nightly": {
        "task": "automana.worker.tasks.ebay.ebay_scrape_external_sold_task",
        "schedule": crontab(hour=7, minute=15),  # 07:15 AEST
    },
    "ebay-promote-sold-obs-nightly": {
        "task": "run_service",
        "schedule": crontab(hour=8, minute=0),   # 08:00 AEST — after sync + scrape
        "kwargs": {"path": "integrations.ebay.promote_sold_obs"},
    },
```

- [ ] **Step 11.3 — Verify tasks import cleanly**

```bash
.venv/bin/python -c "
from automana.worker.tasks.ebay import ebay_sync_own_sales_task, ebay_scrape_external_sold_task
print('Tasks registered:', ebay_sync_own_sales_task.name, ebay_scrape_external_sold_task.name)
" 2>&1
```

Expected:
```
Tasks registered: automana.worker.tasks.ebay.ebay_sync_own_sales_task automana.worker.tasks.ebay.ebay_scrape_external_sold_task
```

- [ ] **Step 11.4 — Commit**

```bash
git add \
  src/automana/worker/tasks/ebay.py \
  src/automana/worker/celeryconfig.py
git commit -m "feat(ebay): add nightly Celery tasks + beat schedule for sales sync and scrape"
```

---

## Task 12: Full Regression + Beat Restart

- [ ] **Step 12.1 — Run full unit test suite**

```bash
.venv/bin/pytest tests/unit/ -q 2>&1 | tail -10
```

Expected: no new failures.

- [ ] **Step 12.2 — Restart Celery beat to pick up new schedule**

```bash
docker compose -f deploy/docker-compose.dev.yml restart celery-beat
```

Wait 5 seconds, then confirm it started and shows the new entries:

```bash
docker logs automana-celery-beat-dev 2>&1 | grep -E "ebay|beat: Starting|Scheduler"
```

Expected: `beat: Starting...` and within 2 minutes the first `Scheduler: Sending due task ebay-*` lines (or no errors if not due yet).

- [ ] **Step 12.3 — Verify DB tables are accessible by app_celery**

```bash
docker exec automana-postgres-dev psql -U app_celery automana -c "
SELECT COUNT(*) FROM app_integration.ebay_active_listings;
SELECT COUNT(*) FROM pricing.ebay_scraped_sold;
" 2>&1
```

Expected: two `count = 0` rows, no permission errors.

- [ ] **Step 12.4 — Final commit**

```bash
git add -A
git status  # confirm only expected files
git commit -m "feat(ebay): complete sold price persistence — both channels wired end-to-end"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] `ebay_active_listings` table — Task 1
- [x] `ebay_scraped_sold` table — Task 1
- [x] `EbaySalesRepository` with `ensure_source_product` — Task 2
- [x] `EbayScrapeSoldRepository` — Task 3
- [x] `get_active_app_code_users` on auth repo — Task 4
- [x] Repo registrations in `service_registry` — Task 5
- [x] Router writes `ebay_active_listings` after listing creation — Task 6
- [x] `track_active_listing` + `sync_own_sales` services — Task 7
- [x] `scrape_external_sold` service — Task 8
- [x] `promote_sold_obs` service — Task 9
- [x] `service_modules` registrations — Task 10
- [x] Celery tasks + beat schedule — Task 11
- [x] title resolution fallback (score_title + suggest) — Task 7
- [x] rate-limit 0.5s between cards in scrape — Task 8
- [x] promotion in batches of 1000 — Task 9
- [x] error handling: per-app_code try/except in sync + scrape — Tasks 7, 8
- [x] best-effort listing tracker in router — Task 6
