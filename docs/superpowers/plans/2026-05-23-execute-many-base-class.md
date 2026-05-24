# `execute_many` Base-Class Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `execute_many` to `AbstractRepository` (and both `QueryExecutor` implementations) so bulk-insert operations go through the same routing, retry, and executor abstraction as `execute_command` instead of calling `self.connection.executemany(...)` directly.

**Architecture:** `QueryExecutor` gets an abstract `execute_many` method implemented by both concrete executors. `AbstractRepository.execute_many` mirrors `execute_command` — it routes through the executor when one is injected, otherwise falls back to `self.connection.executemany`. Four callsites that currently bypass the abstraction are updated to call `self.execute_many`.

**Tech Stack:** Python 3.12, asyncpg, psycopg2, pytest-asyncio

---

## Files

| File | Action | Responsibility |
|------|--------|----------------|
| `src/automana/core/QueryExecutor.py` | Modify | Add abstract `execute_many` + sync/async implementations |
| `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py` | Modify | Add async `execute_many` routing method |
| `src/automana/core/repositories/app_integration/shopify/collection_repository.py` | Modify | Replace direct `connection.executemany` call |
| `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py` | Modify | Replace 2 direct `connection.executemany` calls |
| `src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py` | Modify | Replace direct `connection.executemany` call |
| `tests/unit/core/repositories/abstract/test_execute_many.py` | Create | Unit tests for the new base-class method |

---

### Task 1: Add `execute_many` to `QueryExecutor` and both concrete implementations

**Files:**
- Modify: `src/automana/core/QueryExecutor.py`

**Background:** `QueryExecutor` is the abstract interface for database execution. `SyncQueryExecutor` wraps psycopg2; `AsyncQueryExecutor` wraps asyncpg and adds `InFailedSQLTransactionError` rollback/retry. All three need `execute_many`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/repositories/abstract/test_execute_many.py`:

```python
"""Unit tests for QueryExecutor.execute_many implementations."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call
import asyncpg
import pytest

from automana.core.QueryExecutor import AsyncQueryExecutor


class TestAsyncQueryExecutorExecuteMany:
    async def test_delegates_to_connection_executemany(self):
        conn = AsyncMock()
        executor = AsyncQueryExecutor()
        rows = [("a", 1), ("b", 2)]

        await executor.execute_many(conn, "INSERT INTO t VALUES ($1, $2)", rows)

        conn.executemany.assert_awaited_once_with(
            "INSERT INTO t VALUES ($1, $2)", rows
        )

    async def test_retries_after_failed_transaction_error(self):
        conn = AsyncMock()
        conn.executemany.side_effect = [
            asyncpg.InFailedSQLTransactionError("aborted"),
            None,
        ]
        executor = AsyncQueryExecutor()

        await executor.execute_many(conn, "INSERT INTO t VALUES ($1)", [("x",)])

        assert conn.execute.await_args_list == [call("ROLLBACK")]
        assert conn.executemany.await_count == 2

    async def test_reraises_unknown_exception(self):
        conn = AsyncMock()
        conn.executemany.side_effect = RuntimeError("boom")
        executor = AsyncQueryExecutor()

        with pytest.raises(RuntimeError, match="boom"):
            await executor.execute_many(conn, "INSERT INTO t VALUES ($1)", [("x",)])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana
python -m pytest tests/unit/core/repositories/abstract/test_execute_many.py -v
```

Expected: `AttributeError: 'AsyncQueryExecutor' object has no attribute 'execute_many'`

- [ ] **Step 3: Add `execute_many` to `QueryExecutor`, `SyncQueryExecutor`, and `AsyncQueryExecutor`**

In `src/automana/core/QueryExecutor.py`, add the abstract method to `QueryExecutor` after `execute_query`:

```python
@abstractmethod
def execute_many(
    self,
    query: str,
    rows: List[Tuple[Any, ...]],
) -> None:
    """Execute a bulk command (INSERT/UPDATE) against a list of row tuples."""
    pass
```

Add to `SyncQueryExecutor` after `execute_query`:

```python
def execute_many(
    self,
    connection: connection,
    query: str,
    rows: List[Tuple[Any, ...]],
) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.executemany(query, rows)
            connection.commit()
    except Exception:
        connection.rollback()
        raise
```

Add to `AsyncQueryExecutor` after `execute_query`:

```python
async def execute_many(
    self,
    connection: asyncpg.Connection,
    query: str,
    rows: List[Tuple[Any, ...]],
) -> None:
    try:
        await connection.executemany(query, rows)
    except asyncpg.InFailedSQLTransactionError:
        await connection.execute("ROLLBACK")
        await connection.executemany(query, rows)
    except Exception as e:
        await self._handle_exception(e)
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/core/repositories/abstract/test_execute_many.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/QueryExecutor.py tests/unit/core/repositories/abstract/test_execute_many.py
git commit -m "feat(repositories): add execute_many to QueryExecutor and implementations"
```

---

### Task 2: Add `execute_many` to `AbstractRepository`

**Files:**
- Modify: `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`
- Modify (tests): `tests/unit/core/repositories/abstract/test_execute_many.py`

**Background:** `AbstractRepository.execute_command` routes through the executor when one is injected, else directly hits the connection. `execute_many` follows the same pattern.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/core/repositories/abstract/test_execute_many.py`:

```python
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)
from typing import Optional


class _ConcreteRepo(AbstractRepository[dict]):
    """Minimal concrete subclass to satisfy abstract methods."""
    @property
    def name(self) -> str:
        return "test"

    async def add(self, item): pass
    async def get(self, id): return None
    async def update(self, item): pass
    async def delete(self, id): pass
    async def list(self, items=None): return []


class TestAbstractRepositoryExecuteMany:
    async def test_routes_through_executor_when_present(self):
        conn = AsyncMock()
        executor = AsyncMock()
        repo = _ConcreteRepo(connection=conn, executor=executor)
        rows = [("a", 1)]

        await repo.execute_many("INSERT INTO t VALUES ($1, $2)", rows)

        executor.execute_many.assert_awaited_once_with(
            conn, "INSERT INTO t VALUES ($1, $2)", rows
        )
        conn.executemany.assert_not_awaited()

    async def test_falls_back_to_connection_when_no_executor(self):
        conn = AsyncMock()
        repo = _ConcreteRepo(connection=conn, executor=None)
        rows = [("x",)]

        await repo.execute_many("INSERT INTO t VALUES ($1)", rows)

        conn.executemany.assert_awaited_once_with(
            "INSERT INTO t VALUES ($1)", rows
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/core/repositories/abstract/test_execute_many.py -v -k "TestAbstractRepositoryExecuteMany"
```

Expected: `AttributeError: '_ConcreteRepo' object has no attribute 'execute_many'`

- [ ] **Step 3: Add `execute_many` to `AbstractRepository`**

In `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`, add after `execute_command`:

```python
async def execute_many(self, query: str, rows: list) -> None:
    """Execute a bulk command against a list of row tuples."""
    if self.executor:
        logger.debug("Executing bulk command with executor")
        return await self.executor.execute_many(self.connection, query, rows)
    else:
        logger.debug("Executing bulk command without executor")
        return await self.connection.executemany(query, rows)
```

- [ ] **Step 4: Run all abstract tests**

```bash
python -m pytest tests/unit/core/repositories/abstract/test_execute_many.py -v
```

Expected: all PASSED (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py \
        tests/unit/core/repositories/abstract/test_execute_many.py
git commit -m "feat(repositories): add execute_many to AbstractRepository base class"
```

---

### Task 3: Replace callsites — Shopify collection repo

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/collection_repository.py`

- [ ] **Step 1: Replace the direct call in `add_many`**

In `collection_repository.py`, change `add_many` from:

```python
async def add_many(self, values: List[shopify_theme.InsertCollection]):
    if not values:
        return
    await self.connection.executemany(
        """
        INSERT INTO markets.collection_handles (name, market_id)
        VALUES ($1, $2)
        ON CONFLICT (name, market_id) DO NOTHING;
        """,
        [(v.name, v.market_id) for v in values],
    )
```

to:

```python
async def add_many(self, values: List[shopify_theme.InsertCollection]):
    if not values:
        return
    await self.execute_many(
        """
        INSERT INTO markets.collection_handles (name, market_id)
        VALUES ($1, $2)
        ON CONFLICT (name, market_id) DO NOTHING;
        """,
        [(v.name, v.market_id) for v in values],
    )
```

- [ ] **Step 2: Run the existing test suite to confirm no regressions**

```bash
python -m pytest tests/ -k "shopify or collection" -v
```

Expected: all existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/collection_repository.py
git commit -m "fix(shopify): route add_many through execute_many abstraction"
```

---

### Task 4: Replace callsites — Shopify pipeline repo (2 occurrences)

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py`

There are two `self.connection.executemany` calls: one in `upsert_product_handles` (~line 52) and one in the bulk price-observation insert (~line 167).

- [ ] **Step 1: Replace `upsert_product_handles`**

Change from:

```python
await self.connection.executemany(
    """
    INSERT INTO markets.product_ref (product_shop_id, product_id, market_id, handle, title)
    VALUES ($1, $1, $2, $3, $4)
    ON CONFLICT (product_shop_id)
    DO UPDATE SET handle = EXCLUDED.handle,
                  title  = EXCLUDED.title,
                  updated_at = NOW()
    """,
    [(str(r["product_id"]), r["market_id"], r.get("handle"), r.get("title")) for r in rows],
)
```

to:

```python
await self.execute_many(
    """
    INSERT INTO markets.product_ref (product_shop_id, product_id, market_id, handle, title)
    VALUES ($1, $1, $2, $3, $4)
    ON CONFLICT (product_shop_id)
    DO UPDATE SET handle = EXCLUDED.handle,
                  title  = EXCLUDED.title,
                  updated_at = NOW()
    """,
    [(str(r["product_id"]), r["market_id"], r.get("handle"), r.get("title")) for r in rows],
)
```

- [ ] **Step 2: Replace the bulk price-observation insert (~line 167)**

Change from:

```python
await self.connection.executemany(
    """
    INSERT INTO pricing.price_observation
        (ts_date, price_type_id, finish_id, condition_id, language_id,
         list_low_cents, list_avg_cents, sold_avg_cents, list_count, sold_count,
         source_product_id, data_provider_id, scraped_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    ON CONFLICT DO NOTHING
    """,
    records,
)
```

to:

```python
await self.execute_many(
    """
    INSERT INTO pricing.price_observation
        (ts_date, price_type_id, finish_id, condition_id, language_id,
         list_low_cents, list_avg_cents, sold_avg_cents, list_count, sold_count,
         source_product_id, data_provider_id, scraped_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    ON CONFLICT DO NOTHING
    """,
    records,
)
```

- [ ] **Step 3: Run existing tests**

```bash
python -m pytest tests/ -k "shopify" -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/pipeline_repository.py
git commit -m "fix(shopify): route pipeline repo bulk inserts through execute_many abstraction"
```

---

### Task 5: Replace callsite — `PipelineHealthSnapshotRepository`

**Files:**
- Modify: `src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py`

**Note on the existing test:** `test_pipeline_health_snapshot_repository.py::TestInsertSnapshots::test_calls_executemany_with_one_tuple_per_row` passes `connection = AsyncMock()` with no executor, and asserts `connection.executemany.assert_awaited_once()`. After this change, `execute_many` (with no executor) still calls `self.connection.executemany`, so the test continues to pass without modification — its assertion remains valid.

- [ ] **Step 1: Replace the direct call in `insert_snapshots`**

In `pipeline_health_snapshot_repository.py`, find the line:

```python
await self.connection.executemany(_INSERT_SQL, payload)
```

Replace with:

```python
await self.execute_many(_INSERT_SQL, payload)
```

- [ ] **Step 2: Run the existing snapshot tests**

```bash
python -m pytest tests/unit/core/repositories/ops/test_pipeline_health_snapshot_repository.py -v
```

Expected: all PASS (the test still verifies `connection.executemany` is called, which remains true when no executor is injected)

- [ ] **Step 3: Run the full unit test suite**

```bash
python -m pytest tests/unit/ -v --tb=short
```

Expected: all PASS, no regressions

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py
git commit -m "fix(ops): route health snapshot bulk insert through execute_many abstraction"
```

---

## Self-Review

**Spec coverage:**
- ✅ `execute_many` added to all three `QueryExecutor` classes
- ✅ `execute_many` added to `AbstractRepository` with executor-routing + fallback
- ✅ All 4 direct `self.connection.executemany` callsites replaced
- ✅ `InFailedSQLTransactionError` retry logic included in `AsyncQueryExecutor.execute_many`
- ✅ Existing test for `PipelineHealthSnapshotRepository` continues to pass (connection-level mock still works)

**Placeholder scan:** No TBDs, no "similar to Task N", all code blocks are complete.

**Type consistency:**
- Method signature `execute_many(self, query: str, rows: list)` used consistently across `AbstractRepository` calls
- Executor calls: `executor.execute_many(self.connection, query, rows)` — matches `AsyncQueryExecutor.execute_many(connection, query, rows)` signature throughout
