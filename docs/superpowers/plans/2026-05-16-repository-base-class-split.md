# Repository Base Class Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `AbstractRepository` into `BaseDBRepository` (infrastructure only) and `EntityRepository` (CRUD contract), so domain-specific repos no longer need to stub out methods that make no sense for them.

**Architecture:** A new `BaseDBRepository` abstract class carries only the connection + execute helpers and a `name` property. `EntityRepository` subclasses it and adds the abstract `add/get/update/delete/list` contract. A temporary `AbstractRepository = EntityRepository` alias keeps all existing imports working during the migration. 26 concrete repos are re-pointed: 8 to `EntityRepository`, 18 to `BaseDBRepository` (losing their dead stubs). The alias is removed in the final task.

**Tech Stack:** Python 3.12, asyncpg, ABC/abstractmethod, pytest, AsyncMock

---

## File Map

| Action | File |
|--------|------|
| Modify | `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py` |
| Create | `tests/unit/core/repositories/test_base_db_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/core/repositories/card_catalog/card_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/core/repositories/card_catalog/set_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/core/repositories/card_catalog/collection_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/core/repositories/app_integration/shopify/market_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/core/repositories/app_integration/shopify/collection_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/api/repositories/user_management/user_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/api/repositories/auth/session_repository.py` |
| Modify (→ `EntityRepository`) | `src/automana/api/repositories/user_management/role_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/api/repositories/auth/auth_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/analytics_repositories/analytics_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/metrics_repositories/metrics_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/ops/ops_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/pricing/price_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/mtg_stock/price_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/ebay/auth_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/ebay/app_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/ebay/sales_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/ebay/scope_management_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/ebay/ebay_scrape_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/ebay/listing_actions_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/ebay/listing_builder_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/shopify/price_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/app_integration/shopify/product_repository.py` |
| Modify (→ `BaseDBRepository`) | `src/automana/core/repositories/shop_meta_repository.py` |

---

## Task 1: Refactor AbstractDBRepository.py

**Files:**
- Modify: `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`
- Create: `tests/unit/core/repositories/test_base_db_repository.py`

- [ ] **Step 1: Write the failing smoke tests**

Create `tests/unit/core/repositories/test_base_db_repository.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    BaseDBRepository,
    EntityRepository,
    AbstractRepository,
)


class ConcreteBase(BaseDBRepository):
    @property
    def name(self) -> str:
        return "concrete_base"


class ConcreteEntity(EntityRepository):
    @property
    def name(self) -> str:
        return "concrete_entity"

    async def add(self, item) -> None: ...
    async def get(self, id): return None
    async def update(self, item) -> None: ...
    async def delete(self, id) -> None: ...
    async def list(self, items) -> list: return []


def make_conn():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value=None)
    return conn


def test_base_db_repository_can_be_instantiated():
    repo = ConcreteBase(make_conn())
    assert repo.name == "concrete_base"


def test_entity_repository_can_be_instantiated():
    repo = ConcreteEntity(make_conn())
    assert repo.name == "concrete_entity"


def test_base_db_repository_is_abstract_without_name():
    with pytest.raises(TypeError):
        BaseDBRepository(make_conn())


def test_entity_repository_is_abstract_without_crud():
    class PartialEntity(EntityRepository):
        @property
        def name(self) -> str:
            return "partial"
        async def add(self, item) -> None: ...
        # missing get, update, delete, list

    with pytest.raises(TypeError):
        PartialEntity(make_conn())


def test_abstract_repository_is_alias_for_entity_repository():
    assert AbstractRepository is EntityRepository


def test_entity_repository_is_subclass_of_base():
    assert issubclass(EntityRepository, BaseDBRepository)


def test_concrete_base_inherits_execute_query():
    assert hasattr(ConcreteBase, "execute_query")
    assert hasattr(ConcreteBase, "execute_command")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/repositories/test_base_db_repository.py -v 2>&1 | head -30
```

Expected: `ImportError` or `FAILED` — `BaseDBRepository` and `EntityRepository` don't exist yet.

- [ ] **Step 3: Rewrite `AbstractDBRepository.py`**

Replace the entire file with:

```python
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
import asyncpg, psycopg2
import logging
from typing import Optional, TypeVar, Generic, Union
from automana.core.QueryExecutor import QueryExecutor

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseDBRepository(Generic[T], ABC):
    """Infrastructure base for all DB repositories.

    Provides connection, execute helpers, and a required `name` property.
    Use this for domain-specific repositories (pipelines, analytics, ops)
    that don't expose a generic CRUD interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    def __init__(
        self,
        connection: Union[asyncpg.Connection, psycopg2.extensions.connection],
        executor: QueryExecutor = None,
    ):
        self.connection = connection
        self.executor = executor
        self._thread_pool = ThreadPoolExecutor(max_workers=4)

    def execute_query_sync(self, query, *args):
        if self.executor:
            return self.executor.execute_query(self.connection, query, *args)
        with self.connection.cursor() as cursor:
            cursor.execute(query, args)
            return cursor.fetchall()

    def execute_command_sync(self, query, *args):
        if self.executor:
            return self.executor.execute_command(self.connection, query, *args)
        with self.connection.cursor() as cursor:
            cursor.execute(query, args)
            self.connection.commit()
            return None

    async def execute_query(self, query, values=()):
        if self.executor:
            return await self.executor.execute_query(self.connection, query, values)
        return await self.connection.fetch(query, *values)

    async def execute_command(self, query, values=()):
        if self.executor:
            return await self.executor.execute_command(self.connection, query, values)
        return await self.connection.execute(query, *values)


class EntityRepository(BaseDBRepository[T]):
    """For repositories that manage a single entity type with a CRUD interface.

    Subclass this when your repository needs add/get/update/delete/list.
    For domain-specific repositories, use BaseDBRepository directly.
    """

    @abstractmethod
    async def add(self, item: T) -> None:
        pass

    @abstractmethod
    async def get(self, id: int) -> Optional[T]:
        pass

    @abstractmethod
    async def update(self, item: T) -> None:
        pass

    @abstractmethod
    async def delete(self, id: int) -> None:
        pass

    @abstractmethod
    async def list(self, items: T) -> list[T]:
        pass


# Backward-compat alias — removed in the cleanup task at the end of this plan
AbstractRepository = EntityRepository
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/repositories/test_base_db_repository.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Confirm existing tests still pass**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/ -x -q 2>&1 | tail -15
```

Expected: same pass count as before this task (all passing). `AbstractRepository = EntityRepository` keeps every import working unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py \
        tests/unit/core/repositories/test_base_db_repository.py
git commit -m "refactor(repos): introduce BaseDBRepository and EntityRepository

AbstractRepository is kept as a backward-compat alias for EntityRepository.
All existing imports continue to work without change."
```

---

## Task 2: Migrate Entity Repos — Card Catalog

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py:8-11`
- Modify: `src/automana/core/repositories/card_catalog/set_repository.py:2,10`
- Modify: `src/automana/core/repositories/card_catalog/collection_repository.py:3,7`

These repos implement meaningful CRUD. The only change is the import name. `CollectionRepository` also has a dead `list` stub to remove.

- [ ] **Step 1: Update `card_repository.py`**

Change:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
```
To:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import EntityRepository
```

Change class declaration:
```python
class CardReferenceRepository(AbstractRepository[Any]):
```
To:
```python
class CardReferenceRepository(EntityRepository[Any]):
```

- [ ] **Step 2: Update `set_repository.py`**

Change:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
```
To:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import EntityRepository
```

Change class declaration:
```python
class SetReferenceRepository(AbstractRepository[Any]):
```
To:
```python
class SetReferenceRepository(EntityRepository[Any]):
```

- [ ] **Step 3: Update `collection_repository.py`**

Change import and class:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import EntityRepository
```
```python
class CollectionRepository(EntityRepository):
```

Then find and remove the dead stub (it raises NotImplementedError — not a real implementation):
```python
    async def list():
        raise NotImplementedError("This method is not implemented yet")
```
Replace with:
```python
    async def list(self, items=None) -> list:
        raise NotImplementedError
```
Keep the `raise NotImplementedError` — `list` hasn't been implemented yet but remains part of the EntityRepository contract, so it must be present.

- [ ] **Step 4: Run existing card repo tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/repositories/card_catalog/ -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/card_catalog/
git commit -m "refactor(repos): migrate card catalog repos to EntityRepository"
```

---

## Task 3: Migrate Entity Repos — Shopify + API

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/market_repository.py`
- Modify: `src/automana/core/repositories/app_integration/shopify/collection_repository.py`
- Modify: `src/automana/api/repositories/user_management/user_repository.py`
- Modify: `src/automana/api/repositories/auth/session_repository.py`
- Modify: `src/automana/api/repositories/user_management/role_repository.py`

These repos implement real CRUD operations. The API repos also have a handful of dead stubs to clean up.

- [ ] **Step 1: Update `market_repository.py` and `shopify/collection_repository.py`**

In each file, change:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
```
To:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import EntityRepository
```

And update the class declarations:
- `class MarketRepository(AbstractRepository):` → `class MarketRepository(EntityRepository):`
- `class ShopifyCollectionRepository(AbstractRepository[shopify_theme.CollectionModel]):` → `class ShopifyCollectionRepository(EntityRepository[shopify_theme.CollectionModel]):`

- [ ] **Step 2: Update `user_repository.py`**

Change import and class to use `EntityRepository`. Then find and remove the dead `list` stub at the end of the file:

```python
    async def list(self):
        raise NotImplementedError("Method not implemented yet")
```

Remove those 2 lines entirely — `UserRepository` doesn't expose a `list` operation and `EntityRepository` doesn't require it to work, only to exist. Replace with:

```python
    async def list(self, items=None) -> list:
        raise NotImplementedError
```

- [ ] **Step 3: Update `session_repository.py`**

Change import and class to use `EntityRepository`. Find the `update` stub:

```python
    async def update(self, item):
        raise NotImplementedError("Use rotate_token or invalidate_session for session updates")
```

Keep this stub — the message is useful. But fix the signature to match the contract:

```python
    async def update(self, item) -> None:
        raise NotImplementedError("Use rotate_token or invalidate_session for session updates")
```

Also check if `list` is present. If it only raises NotImplementedError with no body, keep it as:
```python
    async def list(self, items=None) -> list:
        raise NotImplementedError
```

- [ ] **Step 4: Update `role_repository.py`**

Change import and class to use `EntityRepository`. Fix the two methods that `return NotImplementedError(...)` instead of raising it (this is a silent bug — it returns the exception object instead of raising it):

Find:
```python
    async def add(self, role_name: str):
        return NotImplementedError("Method not implemented yet")
    async def list(self):
        return NotImplementedError("Method not implemented yet")
```

Replace with:
```python
    async def add(self, role_name: str) -> None:
        raise NotImplementedError
    async def list(self, items=None) -> list:
        raise NotImplementedError
```

- [ ] **Step 5: Run tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/ -x -q 2>&1 | tail -10
```

Expected: same pass count as before.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/market_repository.py \
        src/automana/core/repositories/app_integration/shopify/collection_repository.py \
        src/automana/api/repositories/user_management/user_repository.py \
        src/automana/api/repositories/auth/session_repository.py \
        src/automana/api/repositories/user_management/role_repository.py
git commit -m "refactor(repos): migrate shopify and API entity repos to EntityRepository

Also fixes RoleRepository.add/list which returned the exception object
instead of raising it."
```

---

## Task 4: Migrate Domain Repos — Analytics, Metrics, Ops

These repos have all-stub CRUD blocks. Migration removes the stubs entirely.

**Files:**
- Modify: `src/automana/core/repositories/analytics_repositories/analytics_repository.py`
- Modify: `src/automana/core/repositories/metrics_repositories/metrics_repository.py`
- Modify: `src/automana/core/repositories/ops/ops_repository.py`
- Modify: `src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py`

- [ ] **Step 1: Update `analytics_repository.py`**

Change import:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import BaseDBRepository
```

Change class:
```python
class AnalyticsRepository(BaseDBRepository):
```

Delete the entire CRUD stub block at the end of the class (the 10 lines containing `async def add`, `async def update`, `async def delete`, `async def get`, `async def list` — all with `pass` bodies).

- [ ] **Step 2: Update `metrics_repository.py`**

Change import and class to use `BaseDBRepository`. Delete the CRUD stub block (lines marked `# Abstract methods required by AbstractRepository` through the end of the class — the 10 lines with `raise NotImplementedError`).

- [ ] **Step 3: Update `ops_repository.py`**

Change import and class to use `BaseDBRepository`. Delete the CRUD stub block at the end of the class (the `get`, `add`, `update`, `delete`, `list` methods that all raise `NotImplementedError`).

- [ ] **Step 4: Update `pipeline_health_snapshot_repository.py`**

Change import:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    BaseDBRepository,
)
```

Change class:
```python
class PipelineHealthSnapshotRepository(BaseDBRepository[PipelineHealthSnapshotRow]):
```

Delete the CRUD stub block (the `add`, `get`, `update`, `delete`, `list` methods marked `# pragma: no cover - not used`).

Also remove the comment in the module docstring that says "Conforms to the project's AbstractRepository pattern" — update it to say "Extends BaseDBRepository."

- [ ] **Step 5: Run tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/repositories/ops/ -v
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/analytics_repositories/ \
        src/automana/core/repositories/metrics_repositories/ \
        src/automana/core/repositories/ops/
git commit -m "refactor(repos): migrate analytics/metrics/ops repos to BaseDBRepository

Removes ~30 lines of CRUD stubs that had no implementations."
```

---

## Task 5: Migrate Domain Repos — Pipelines (MTGJson, MTGStock, Pricing)

**Files:**
- Modify: `src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py`
- Modify: `src/automana/core/repositories/app_integration/mtg_stock/price_repository.py`
- Modify: `src/automana/core/repositories/pricing/price_repository.py`

`PricingTierRepository` is the critical one — it currently extends `AbstractRepository` but doesn't implement the abstract methods, making it **impossible to instantiate** (Python raises `TypeError`). This task fixes that bug.

- [ ] **Step 1: Update `mtgjson_repository.py`**

Change import:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import BaseDBRepository
```

Change class:
```python
class MtgjsonRepository(BaseDBRepository):
```

Delete the CRUD stub block at the end of the file — the section labeled `# AbstractRepository contract` containing `add`, `get`, `list`, `update`, `delete` — all raise `NotImplementedError`.

- [ ] **Step 2: Update `mtg_stock/price_repository.py`**

Change import and class to `BaseDBRepository`. Delete the `add`, `delete`, `update`, `get`, `list` stub block at the bottom of the class (all raise `NotImplementedError("Method not implemented")`).

- [ ] **Step 3: Update `pricing/price_repository.py`**

Change import and class to `BaseDBRepository`:

```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import BaseDBRepository
```

```python
class PricingTierRepository(BaseDBRepository):
```

`PricingTierRepository` had no CRUD stubs at all — that's why it was broken. After this change it will be instantiable.

- [ ] **Step 4: Write and run the instantiation test**

Add this test to `tests/unit/core/repositories/test_base_db_repository.py`:

```python
from unittest.mock import MagicMock
from automana.core.repositories.pricing.price_repository import PricingTierRepository


def test_pricing_tier_repository_can_be_instantiated():
    """PricingTierRepository was previously broken — AbstractRepository forced
    abstract CRUD methods that it never implemented."""
    conn = MagicMock()
    repo = PricingTierRepository(conn)
    assert repo.name == "PriceRepository"
```

Run:
```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/repositories/test_base_db_repository.py -v
```

Expected: all tests PASS including the new one.

- [ ] **Step 5: Run pipeline repo tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest \
  tests/unit/core/repositories/app_integration/mtgjson/ \
  tests/unit/core/repositories/app_integration/mtg_stock/ \
  tests/unit/core/repositories/pricing/ \
  -v
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py \
        src/automana/core/repositories/app_integration/mtg_stock/price_repository.py \
        src/automana/core/repositories/pricing/price_repository.py \
        tests/unit/core/repositories/test_base_db_repository.py
git commit -m "fix(repos): PricingTierRepository was uninstantiable due to missing abstract methods

Migrates MtgjsonRepository, MtgStock PriceRepository, and PricingTierRepository
to BaseDBRepository. PricingTierRepository previously extended AbstractRepository
without implementing any of the abstract CRUD methods."
```

---

## Task 6: Migrate Domain Repos — eBay DB Repos

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/auth_repository.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/app_repository.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/sales_repository.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/scope_management_repository.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/ebay_scrape_repository.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/listing_actions_repository.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/listing_builder_repository.py`

For each file: change import to `BaseDBRepository`, update class declaration, and delete CRUD stubs.

**Important:** Before deleting a stub method, read its body. If it's only `pass` or `raise NotImplementedError`, delete it. If it contains real logic (even partially), keep it as a regular method on `BaseDBRepository`.

- [ ] **Step 1: Update `ebay/auth_repository.py`**

Change import and class:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import BaseDBRepository
class EbayAuthRepository(BaseDBRepository):
```

Locate the comment `# AbstractRepository stubs` and delete everything from that comment to the end of the class. These are all `raise NotImplementedError` stubs.

- [ ] **Step 2: Update `ebay/app_repository.py`**

Change import and class to `BaseDBRepository`.

Read the `add`, `get`, `update`, `delete`, `list` method bodies:
- `add` and `get` — if they have real SQL logic, keep them (they become plain methods on `BaseDBRepository`)
- `update`, `delete`, `list`, `get_many` — if they only `raise NotImplementedError`, delete them

- [ ] **Step 3: Update `ebay/sales_repository.py`**

Change import:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    BaseDBRepository,
)
```

Change class:
```python
class EbaySalesRepository(BaseDBRepository):
```

Delete the `add`, `update`, `delete`, `list` stubs at the top of the class (all `pass`). The `get` stub returns `None` silently — check if it's used anywhere before deleting; if not, delete it too.

- [ ] **Step 4: Update `ebay/scope_management_repository.py`**

Change import and class to `BaseDBRepository`. Read the `add`, `update`, `delete`, `get` method bodies — if they only have `pass` or `raise NotImplementedError`, delete them. If they have real logic, keep them.

- [ ] **Step 5: Update `ebay/ebay_scrape_repository.py`**

Change import:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    BaseDBRepository,
)
```

Change class:
```python
class EbayScrapeSoldRepository(BaseDBRepository):
```

Delete the `add`, `update`, `delete`, `list` stubs (all `pass`). Check `get` — if it returns `None` silently with no logic, delete it too.

- [ ] **Step 6: Update `ebay/listing_actions_repository.py`**

Change import and class to `BaseDBRepository`. Delete the `add`, `update`, `delete`, `list` stubs (all `pass`). Check `get` body.

- [ ] **Step 7: Update `ebay/listing_builder_repository.py`**

Change import:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    BaseDBRepository,
)
```

Change class:
```python
class EbayListingBuilderRepository(BaseDBRepository):
```

Delete the full CRUD stub block (all raise `NotImplementedError`).

- [ ] **Step 8: Run eBay repo tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest \
  tests/unit/core/repositories/app_integration/ebay/ \
  -v
```

Expected: all passing.

- [ ] **Step 9: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/
git commit -m "refactor(repos): migrate eBay DB repos to BaseDBRepository

Removes CRUD stubs from auth, app, sales, scope, scrape, listing_actions,
and listing_builder repositories."
```

---

## Task 7: Migrate Domain Repos — Shopify Price/Product + Auth + ShopMeta

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/price_repository.py`
- Modify: `src/automana/core/repositories/app_integration/shopify/product_repository.py`
- Modify: `src/automana/api/repositories/auth/auth_repository.py`
- Modify: `src/automana/core/repositories/shop_meta_repository.py`

- [ ] **Step 1: Update `shopify/price_repository.py`**

Read the file first to check which methods are stubs vs real. Then:

Change import and class:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import BaseDBRepository
class ShopifyPriceRepository(BaseDBRepository):
```

Delete any stub methods (only `pass` or `raise NotImplementedError` bodies).

- [ ] **Step 2: Update `shopify/product_repository.py`**

Change import and class to `BaseDBRepository`. Delete the entire `add`, `delete`, `get`, `list`, `update` stub block (all raise `NotImplementedError("Method not implemented yet")`).

- [ ] **Step 3: Update `api/auth/auth_repository.py`**

Read the file first. If it has no real CRUD implementations (the grep showed no method bodies), change to `BaseDBRepository`. If it has real `add`/`get`/etc., switch to `EntityRepository` instead.

Change import based on what you find:
```python
# If domain-specific:
from automana.core.repositories.abstract_repositories.AbstractDBRepository import BaseDBRepository
class AuthRepository(BaseDBRepository):

# If real CRUD:
from automana.core.repositories.abstract_repositories.AbstractDBRepository import EntityRepository
class AuthRepository(EntityRepository):
```

Delete any stubs if moving to `BaseDBRepository`.

- [ ] **Step 4: Update `shop_meta_repository.py`**

`ThemeRepository` uses domain-specific method names (`add_theme`, `delete_theme`, `get_theme`, `update_theme`) rather than the CRUD interface. Switch to `BaseDBRepository`.

Change import and class:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import BaseDBRepository
class ThemeRepository(BaseDBRepository[Theme]):
```

Note: `ShopMetaDataRepository` in the same file does **not** extend `AbstractRepository` — leave it unchanged.

- [ ] **Step 5: Run full unit test suite**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/ -q 2>&1 | tail -10
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/price_repository.py \
        src/automana/core/repositories/app_integration/shopify/product_repository.py \
        src/automana/api/repositories/auth/auth_repository.py \
        src/automana/core/repositories/shop_meta_repository.py
git commit -m "refactor(repos): migrate shopify price/product, auth, and shop_meta to BaseDBRepository"
```

---

## Task 8: Remove the Backward-Compat Alias

With all repos updated, the `AbstractRepository = EntityRepository` alias is no longer needed.

**Files:**
- Modify: `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`

- [ ] **Step 1: Verify no remaining usages of `AbstractRepository`**

```bash
grep -rn "AbstractRepository" /home/arthur/projects/AutoMana/src/ --include="*.py" | grep -v "__pycache__" | grep -v "AbstractDBRepository.py"
```

Expected: **no output**. If any files still appear, update them before proceeding.

- [ ] **Step 2: Remove the alias line from `AbstractDBRepository.py`**

Find and delete:
```python
# Backward-compat alias — removed in the cleanup task at the end of this plan
AbstractRepository = EntityRepository
```

- [ ] **Step 3: Update the test**

In `tests/unit/core/repositories/test_base_db_repository.py`, remove:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    BaseDBRepository,
    EntityRepository,
    AbstractRepository,
)
```

Replace with:
```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    BaseDBRepository,
    EntityRepository,
)
```

And delete the test:
```python
def test_abstract_repository_is_alias_for_entity_repository():
    assert AbstractRepository is EntityRepository
```

- [ ] **Step 4: Run full test suite**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py \
        tests/unit/core/repositories/test_base_db_repository.py
git commit -m "refactor(repos): remove AbstractRepository backward-compat alias

All 26 concrete repositories now import BaseDBRepository or EntityRepository
directly. AbstractRepository is no longer exported."
```
