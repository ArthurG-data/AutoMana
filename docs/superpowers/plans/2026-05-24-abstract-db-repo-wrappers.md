# Abstract DB Repository Wrappers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate every direct `self.connection.*` call from concrete DB repositories by adding the missing wrapper methods to `AbstractRepository` so all query primitives go through one interface.

**Architecture:** `AbstractRepository` already wraps `fetch`, `execute`, and `executemany`. Seven primitives (`fetchrow`, `fetchval`, `copy_to_table`, `copy_records_to_table`, stored-procedure `CALL`, `transaction()`, and `add/remove_listener`) are used directly on `self.connection` in 9 concrete repos. We add these wrappers to the abstract, then do a mechanical substitution pass across all affected repos. No behaviour change — the fallback path calls the same asyncpg method; only the call site changes.

**Tech Stack:** Python 3.11+, asyncpg, psycopg2, pytest-asyncio

---

## ⚠️ Improvements To Flag (not bugs in this plan — separate follow-ups)

| # | File | Problem | Recommended follow-up |
|---|---|---|---|
| I1 | `QueryExecutor` | Interface has `execute_query`/`execute_command`/`execute_many` only. New wrappers go direct to `self.connection` and bypass the executor's retry/error-handling logic (`InFailedSQLTransactionError` ROLLBACK). | Add `execute_fetchrow` / `execute_fetchval` to `QueryExecutor` + `AsyncQueryExecutor` in a separate PR. |
| I2 | All non-CRUD repos | `add`, `get`, `update`, `delete`, `list` are abstract and force every pipeline repo to paste `raise NotImplementedError` stubs. Already tracked in `docs/superpowers/plans/2026-05-16-repository-base-class-split.md`. | Use that plan. |
| I3 | `shopify/product_repository.py:7` | `def __init__(self, connection, executor: None)` — `None` is a type annotation, not a default. `executor` is a required positional arg, so `ProductRepository(conn)` raises `TypeError`. | Fix to `executor=None`. Fixed in Task 6 of this plan. |
| I4 | `shopify/product_repository.py:19` | `copy_to_table("pricing.shopify_staging_raw", ...)` passes dotted `schema.table` as `table_name`. asyncpg requires `table_name="shopify_staging_raw", schema_name="pricing"` separately. This is a pre-existing runtime bug, not introduced by this plan. | Fix when `ProductRepository._copy_to_table` is used in production. |
| I5 | `shopify/market_repository.py:62-66` | Misaligned indentation: `# Construct the final query` and `await self.connection.execute(query, *values)` are at class level rather than method body. The `update` method silently does nothing if `set_clauses` is empty because the execute is unreachable outside the `if` block. | Audit and fix indentation. |
| I6 | `pricing/price_repository.py:577-590` | `PricingTierRepository.execute_procedure` hardcodes `timeout=7200`. Removing the local override (Task 5) drops the per-query timeout; the service-level `command_timeout` in `ServiceManager._execute_service` becomes the only guard. Per CLAUDE.md this is the correct approach — but verify `refresh_daily_prices` and `archive_to_weekly` have a matching `command_timeout` registered in `service_manager.py` before merging Task 5. |

---

## File Map

| File | Change |
|---|---|
| `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py` | Add 8 new wrapper methods |
| `src/automana/core/repositories/app_integration/mtg_stock/price_repository.py` | 9 call sites → wrappers |
| `src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py` | 3 call sites → wrappers |
| `src/automana/core/repositories/card_catalog/card_repository.py` | 5 call sites → wrappers |
| `src/automana/core/repositories/pricing/price_repository.py` | 16 call sites → wrappers; remove local `execute_procedure` |
| `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py` | 12 call sites → wrappers; add `__init__` |
| `src/automana/core/repositories/app_integration/shopify/market_repository.py` | 3 call sites → wrappers |
| `src/automana/core/repositories/app_integration/shopify/collection_repository.py` | 1 call site → wrapper |
| `src/automana/core/repositories/app_integration/shopify/product_repository.py` | 1 call site → wrapper; fix `executor: None` → `executor=None` |
| `src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py` | 1 call site → wrapper |
| `src/automana/tests/unit/repositories/test_abstract_repository.py` | New — unit tests for all 8 new wrappers |

---

## Task 1: Add missing wrappers to `AbstractRepository`

**Files:**
- Modify: `src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`
- Create: `src/automana/tests/unit/repositories/test_abstract_repository.py`

> **Note on executor routing:** `QueryExecutor` only defines `execute_query`, `execute_command`, `execute_many`. The new wrappers call `self.connection` directly — the executor is not involved. A comment in each wrapper documents this so a future engineer doesn't wonder why the executor is skipped.

- [ ] **Step 1: Write the failing tests**

```python
# src/automana/tests/unit/repositories/test_abstract_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository


class ConcreteRepo(AbstractRepository):
    @property
    def name(self): return "test"
    async def add(self, item): pass
    async def get(self, id): pass
    async def update(self, item): pass
    async def delete(self, id): pass
    async def list(self, items): pass


@pytest.mark.asyncio
async def test_execute_fetchrow_delegates_to_connection():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": 1})
    repo = ConcreteRepo(connection=conn)
    result = await repo.execute_fetchrow("SELECT 1", (42,))
    conn.fetchrow.assert_awaited_once_with("SELECT 1", 42)
    assert result == {"id": 1}


@pytest.mark.asyncio
async def test_execute_fetchrow_no_args():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    repo = ConcreteRepo(connection=conn)
    await repo.execute_fetchrow("SELECT now()")
    conn.fetchrow.assert_awaited_once_with("SELECT now()")


@pytest.mark.asyncio
async def test_execute_fetchval_delegates_to_connection():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=5)
    repo = ConcreteRepo(connection=conn)
    result = await repo.execute_fetchval("SELECT COUNT(*) FROM t", ())
    conn.fetchval.assert_awaited_once_with("SELECT COUNT(*) FROM t")
    assert result == 5


@pytest.mark.asyncio
async def test_execute_copy_to_table_passes_kwargs():
    conn = AsyncMock()
    conn.copy_to_table = AsyncMock(return_value="COPY 10")
    repo = ConcreteRepo(connection=conn)
    buf = MagicMock()
    await repo.execute_copy_to_table("my_table", buf, schema_name="myschema", format="csv")
    conn.copy_to_table.assert_awaited_once_with(
        table_name="my_table", source=buf, schema_name="myschema", format="csv"
    )


@pytest.mark.asyncio
async def test_execute_copy_records_to_table_delegates():
    conn = AsyncMock()
    conn.copy_records_to_table = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    records = [("a", 1), ("b", 2)]
    await repo.execute_copy_records_to_table(
        "my_table", records=records, columns=("col1", "col2"), schema_name="s"
    )
    conn.copy_records_to_table.assert_awaited_once_with(
        "my_table", records=records, columns=("col1", "col2"), schema_name="s"
    )


@pytest.mark.asyncio
async def test_execute_procedure_no_args():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    await repo.execute_procedure("myschema.my_proc")
    conn.execute.assert_awaited_once_with("CALL myschema.my_proc()", timeout=None)


@pytest.mark.asyncio
async def test_execute_procedure_with_args_and_timeout():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    await repo.execute_procedure("pricing.refresh", ("2024-01-01", "2024-12-31"), timeout=3600)
    conn.execute.assert_awaited_once_with(
        "CALL pricing.refresh($1, $2)", "2024-01-01", "2024-12-31", timeout=3600
    )


@pytest.mark.asyncio
async def test_transaction_returns_connection_transaction():
    conn = MagicMock()
    tx = MagicMock()
    conn.transaction = MagicMock(return_value=tx)
    repo = ConcreteRepo(connection=conn)
    result = repo.transaction()
    conn.transaction.assert_called_once()
    assert result is tx


@pytest.mark.asyncio
async def test_add_listener_delegates():
    conn = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    cb = MagicMock()
    await repo.add_listener("my_channel", cb)
    conn.add_listener.assert_awaited_once_with("my_channel", cb)


@pytest.mark.asyncio
async def test_remove_listener_delegates():
    conn = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    cb = MagicMock()
    await repo.remove_listener("my_channel", cb)
    conn.remove_listener.assert_awaited_once_with("my_channel", cb)
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd src && python -m pytest automana/tests/unit/repositories/test_abstract_repository.py -v
```

Expected: `AttributeError: 'ConcreteRepo' object has no attribute 'execute_fetchrow'` (or similar) on all new tests.

- [ ] **Step 3: Add the 8 new methods to `AbstractRepository`**

In `AbstractDBRepository.py`, after the `execute_many` method (line 78), add:

```python
    async def execute_fetchrow(self, query: str, values: tuple = ()):
        # QueryExecutor doesn't define fetchrow — goes direct to connection.
        return await self.connection.fetchrow(query, *values)

    async def execute_fetchval(self, query: str, values: tuple = ()):
        # QueryExecutor doesn't define fetchval — goes direct to connection.
        return await self.connection.fetchval(query, *values)

    async def execute_copy_to_table(self, table_name: str, source, **kwargs):
        # COPY is asyncpg-specific; not routable through QueryExecutor.
        return await self.connection.copy_to_table(
            table_name=table_name, source=source, **kwargs
        )

    async def execute_copy_records_to_table(
        self, table_name: str, *, records, columns, schema_name: str
    ):
        # COPY is asyncpg-specific; not routable through QueryExecutor.
        return await self.connection.copy_records_to_table(
            table_name, records=records, columns=columns, schema_name=schema_name
        )

    async def execute_procedure(
        self, proc_name: str, args: tuple = (), timeout: float | None = None
    ) -> None:
        """Execute a stored procedure via CALL. Use service-level command_timeout for long ops."""
        placeholders = ", ".join(f"${i + 1}" for i in range(len(args)))
        call_stmt = f"CALL {proc_name}({placeholders})"
        await self.connection.execute(call_stmt, *args, timeout=timeout)

    def transaction(self):
        """Return an asyncpg transaction context manager."""
        return self.connection.transaction()

    async def add_listener(self, channel: str, callback) -> None:
        await self.connection.add_listener(channel, callback)

    async def remove_listener(self, channel: str, callback) -> None:
        await self.connection.remove_listener(channel, callback)
```

- [ ] **Step 4: Run the tests — all should pass**

```bash
cd src && python -m pytest automana/tests/unit/repositories/test_abstract_repository.py -v
```

Expected: 10 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py \
        src/automana/tests/unit/repositories/test_abstract_repository.py
git commit -m "feat(repo): add execute_fetchrow/fetchval/copy/procedure/transaction/listener wrappers to AbstractRepository"
```

---

## Task 2: Pilot — `app_integration/mtg_stock/price_repository.py`

Validates the pattern on the smallest file that exercises the most primitives (5: `execute`, `copy_to_table`, `fetchrow`, `add_listener`, `remove_listener`).

**Files:**
- Modify: `src/automana/core/repositories/app_integration/mtg_stock/price_repository.py`

- [ ] **Step 1: Apply substitutions**

| Line | Before | After |
|---|---|---|
| 20 | `await self.connection.execute("ROLLBACK;")` | `await self.execute_command("ROLLBACK;")` |
| 40–46 | `await self.connection.copy_to_table(table_name=table_name, schema_name=schema_name, source=buf, format='csv', header=True)` | `await self.execute_copy_to_table(table_name, buf, schema_name=schema_name, format='csv', header=True)` |
| 63 | `await self.connection.execute("SET timescaledb...")` | `await self.execute_command("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0")` |
| 67–72 | `await self.connection.execute("CALL pricing.load_staging_prices_batched($1::varchar, $2::int, $3::int);", source_name, batch_days, ingestion_run_id)` | `await self.execute_command("CALL pricing.load_staging_prices_batched($1::varchar, $2::int, $3::int);", (source_name, batch_days, ingestion_run_id))` |
| 74 | `await self.connection.execute("RESET timescaledb...")` | `await self.execute_command("RESET timescaledb.max_tuples_decompressed_per_dml_transaction")` |
| 88–91 | `row = await self.connection.fetchrow("SELECT pricing.resolve_price_rejects($1::int, $2::boolean) AS rows_resolved;", limit, only_unresolved)` | `row = await self.execute_fetchrow("SELECT pricing.resolve_price_rejects($1::int, $2::boolean) AS rows_resolved;", (limit, only_unresolved))` |
| 106 | `await self.connection.add_listener('staging_log', _on_notify)` | `await self.add_listener('staging_log', _on_notify)` |
| 107–110 | `await self.connection.execute("CALL pricing.load_prices_from_staged_batched($1::int);", batch_days)` | `await self.execute_command("CALL pricing.load_prices_from_staged_batched($1::int);", (batch_days,))` |
| 114 | `await self.connection.remove_listener('staging_log', _on_notify)` | `await self.remove_listener('staging_log', _on_notify)` |

- [ ] **Step 2: Verify no `self.connection.` remains**

```bash
grep -n "self\.connection\." src/automana/core/repositories/app_integration/mtg_stock/price_repository.py
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/repositories/app_integration/mtg_stock/price_repository.py
git commit -m "refactor(repo): route mtg_stock PriceRepository through abstract wrappers"
```

---

## Task 3: `app_integration/mtgjson/mtgjson_repository.py`

**Files:**
- Modify: `src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py`

- [ ] **Step 1: Apply substitutions**

| Line | Before | After |
|---|---|---|
| 37 | `await self.connection.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock_name)` | `await self.execute_command("SELECT pg_advisory_xact_lock(hashtext($1))", (lock_name,))` |
| 50–55 | `await self.connection.copy_records_to_table("mtgjson_card_prices_staging", records=records, columns=_STAGING_COLUMNS, schema_name="pricing")` | `await self.execute_copy_records_to_table("mtgjson_card_prices_staging", records=records, columns=_STAGING_COLUMNS, schema_name="pricing")` |
| 73–101 | `count = await self.connection.fetchval("""...""", mtgjson_uuids, scryfall_uuids)` | `count = await self.execute_fetchval("""...""", (mtgjson_uuids, scryfall_uuids))` |

- [ ] **Step 2: Verify**

```bash
grep -n "self\.connection\." src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py
git commit -m "refactor(repo): route MtgjsonRepository through abstract wrappers"
```

---

## Task 4: `card_catalog/card_repository.py`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py`

- [ ] **Step 1: Apply substitutions**

**Line 47–59 (`_copy_csv_to_table`):**
```python
# Before:
status = await self.connection.copy_to_table(
    table_name=table_name,
    schema_name=schema_name,
    source=data_mv,
    format='csv',
    null='',
    delimiter='\t',
    header=False
)

# After:
status = await self.execute_copy_to_table(
    table_name,
    data_mv,
    schema_name=schema_name,
    format='csv',
    null='',
    delimiter='\t',
    header=False,
)
```

**Lines 976–986 (migration staging transaction):**
```python
# Before:
async with self.connection.transaction():
    await self.connection.execute(create_staging_sql)
    copy_status = await self.connection.copy_to_table(
        table_name=staging_table,
        source=data_mv,
        format="csv",
        null="",
        delimiter="\t",
        header=False,
    )
    insert_status = await self.connection.execute(promote_sql)

# After:
async with self.transaction():
    await self.execute_command(create_staging_sql)
    copy_status = await self.execute_copy_to_table(
        staging_table,
        data_mv,
        format="csv",
        null="",
        delimiter="\t",
        header=False,
    )
    insert_status = await self.execute_command(promote_sql)
```

**Line 1143:**
```python
# Before:
status = await self.connection.execute(sql, scryfall_ids, uri_jsons)

# After:
status = await self.execute_command(sql, (scryfall_ids, uri_jsons))
```

- [ ] **Step 2: Verify**

```bash
grep -n "self\.connection\." src/automana/core/repositories/card_catalog/card_repository.py
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py
git commit -m "refactor(repo): route CardReferenceRepository through abstract wrappers"
```

---

## Task 5: `core/repositories/pricing/price_repository.py`

This is the largest file (two classes). Also removes the local `execute_procedure` override from `PricingTierRepository`.

> **⚠️ Before merging:** verify that `refresh_daily_prices` and `archive_to_weekly` service registrations in `service_manager.py` have a `command_timeout` set — the local `timeout=7200` on the old `execute_procedure` will be removed and service-level timeout becomes the only guard (see Improvement I6 above).

**Files:**
- Modify: `src/automana/core/repositories/pricing/price_repository.py`

- [ ] **Step 1: Apply substitutions in `PricingTierRepository`**

**`get_card_current_prices` (line 219):**
```python
# Before:
rows = await self.connection.fetch(_GET_CARD_CURRENT_PRICES_SQL, card_version_id)
# After:
rows = await self.execute_query(_GET_CARD_CURRENT_PRICES_SQL, (card_version_id,))
```

**`get_price_history` (line 236):**
```python
# Before:
rows = await self.connection.fetch(_GET_PRICE_HISTORY_SQL, card_version_id, finish_id, condition_id, days)
# After:
rows = await self.execute_query(_GET_PRICE_HISTORY_SQL, (card_version_id, finish_id, condition_id, days))
```

**`refresh_card_price_spark` (line 313):**
```python
# Before:
await self.connection.execute("CALL pricing.refresh_card_price_spark()")
# After:
await self.execute_procedure("pricing.refresh_card_price_spark")
```

**`upsert_scryfall_price_batch` (lines 342, 365, 378, 403, 410, 439):**
```python
# Line 342 — Before:
resolved = await self.connection.fetch(_RESOLVE_SCRYFALL_IDS_SQL, scryfall_ids)
# After:
resolved = await self.execute_query(_RESOLVE_SCRYFALL_IDS_SQL, (scryfall_ids,))

# Line 365 — Before:
new_rows = await self.connection.fetch(_INSERT_PRODUCTS_BATCH_SQL, unlinked_cv_ids)
# After:
new_rows = await self.execute_query(_INSERT_PRODUCTS_BATCH_SQL, (unlinked_cv_ids,))

# Line 378 — Before:
existing = await self.connection.fetch(_GET_PRODUCT_IDS_FOR_CARDS_SQL, still_missing_cv_ids)
# After:
existing = await self.execute_query(_GET_PRODUCT_IDS_FOR_CARDS_SQL, (still_missing_cv_ids,))

# Line 403 — Before:
await self.connection.execute(_ENSURE_SOURCE_PRODUCT_SQL, sp_product_ids, sp_source_codes)
# After:
await self.execute_command(_ENSURE_SOURCE_PRODUCT_SQL, (sp_product_ids, sp_source_codes))

# Line 410 — Before:
sp_rows = await self.connection.fetch(_FETCH_SOURCE_PRODUCT_IDS_SQL, unique_product_ids, unique_source_codes)
# After:
sp_rows = await self.execute_query(_FETCH_SOURCE_PRODUCT_IDS_SQL, (unique_product_ids, unique_source_codes))

# Line 439 — Before:
status = await self.connection.execute(_UPSERT_PRICE_OBSERVATION_SQL, ts_date, obs_source_product_ids, obs_finish_codes, obs_price_cents)
# After:
status = await self.execute_command(_UPSERT_PRICE_OBSERVATION_SQL, (ts_date, obs_source_product_ids, obs_finish_codes, obs_price_cents))
```

**`upsert_opentcg_price_batch` (lines 468, 489, 501, 520, 525, 561):**
```python
# Line 468:
resolved = await self.execute_query(_RESOLVE_TCGPLAYER_IDS_SQL, (tcgplayer_ids,))

# Line 489:
new_rows = await self.execute_query(_INSERT_PRODUCTS_BATCH_SQL, (unlinked_cv_ids,))

# Line 501:
existing = await self.execute_query(_GET_PRODUCT_IDS_FOR_CARDS_SQL, (still_missing,))

# Line 520:
await self.execute_command(_ENSURE_SOURCE_PRODUCT_SQL, (sp_product_ids, sp_source_codes))

# Line 525:
sp_rows = await self.execute_query(_FETCH_SOURCE_PRODUCT_IDS_SQL, (unique_product_ids, unique_source_codes))

# Line 561:
status = await self.execute_command(
    _UPSERT_OPENTCG_PRICE_OBSERVATION_SQL,
    (ts_date, obs_sp_ids, obs_finish_codes, obs_condition_codes,
     obs_language_codes, obs_list_avg, obs_list_low, obs_list_count),
)
```

- [ ] **Step 2: Remove the local `execute_procedure` override (lines 577–590)**

Delete the entire method — the abstract now provides it. The callers (`refresh_daily_prices`, `archive_to_weekly`) will resolve to the abstract's implementation with `timeout=None`.

- [ ] **Step 3: Verify**

```bash
grep -n "self\.connection\." src/automana/core/repositories/pricing/price_repository.py
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/repositories/pricing/price_repository.py
git commit -m "refactor(repo): route PricingTierRepository through abstract wrappers; remove local execute_procedure"
```

---

## Task 6: Shopify repositories (4 files)

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py`
- Modify: `src/automana/core/repositories/app_integration/shopify/market_repository.py`
- Modify: `src/automana/core/repositories/app_integration/shopify/collection_repository.py`
- Modify: `src/automana/core/repositories/app_integration/shopify/product_repository.py`

- [ ] **Step 1: `pipeline_repository.py` — add missing `__init__` and replace 12 call sites**

Add `__init__` at the top of `ShopifyPipelineRepository`:
```python
def __init__(self, connection, executor=None):
    super().__init__(connection, executor)
```

Then apply substitutions:

| Line | Before | After |
|---|---|---|
| 35 | `rows = await self.connection.fetch("""SELECT...""")` | `rows = await self.execute_query("""SELECT...""")` |
| 68 | `rows = await self.connection.fetch("""SELECT...""", tcg_ids)` | `rows = await self.execute_query("""SELECT...""", (tcg_ids,))` |
| 96 | `await self.connection.execute("""WITH need AS...""", card_version_ids)` | `await self.execute_command("""WITH need AS...""", (card_version_ids,))` |
| 126 | `await self.connection.execute("""INSERT INTO pricing.source_product...""", card_version_ids, source_id)` | `await self.execute_command("""INSERT INTO pricing.source_product...""", (card_version_ids, source_id))` |
| 138 | `rows = await self.connection.fetch("""SELECT mcp...""", card_version_ids, source_id)` | `rows = await self.execute_query("""SELECT mcp...""", (card_version_ids, source_id))` |
| 181 | `await self.connection.execute("TRUNCATE pricing.shopify_staging_raw;")` | `await self.execute_command("TRUNCATE pricing.shopify_staging_raw;")` |
| 185 | `rows = await self.connection.fetch("""SELECT product_id...""")` | `rows = await self.execute_query("""SELECT product_id...""")` |
| 196 | `sell_type = await self.connection.fetchrow("SELECT transaction_type_id...")` | `sell_type = await self.execute_fetchrow("SELECT transaction_type_id...")` |
| 199 | `dp = await self.connection.fetchrow("SELECT data_provider_id...")` | `dp = await self.execute_fetchrow("SELECT data_provider_id...")` |
| 202 | `lang = await self.connection.fetchrow("SELECT language_id...")` | `lang = await self.execute_fetchrow("SELECT language_id...")` |
| 205 | `conditions = await self.connection.fetch("SELECT code, condition_id FROM pricing.card_condition")` | `conditions = await self.execute_query("SELECT code, condition_id FROM pricing.card_condition")` |
| 208 | `finishes = await self.connection.fetch("SELECT code, finish_id FROM card_catalog.card_finished")` | `finishes = await self.execute_query("SELECT code, finish_id FROM card_catalog.card_finished")` |

- [ ] **Step 2: `market_repository.py` — replace 3 call sites**

| Line | Before | After |
|---|---|---|
| 32 | `result = await self.connection.fetchrow(queries.select_market_id_query, id)` | `result = await self.execute_fetchrow(queries.select_market_id_query, (id,))` |
| 66 | `await self.connection.execute(query, *values)` | `await self.execute_command(query, tuple(values))` |
| 70–75 | `await self.connection.execute("""DELETE FROM markets WHERE market_id = $1;""", id)` | `await self.execute_command("""DELETE FROM markets WHERE market_id = $1;""", (id,))` |
| 81 | `rows = await self.connection.fetch(queries.select_all_markets_query)` | `rows = await self.execute_query(queries.select_all_markets_query)` |

- [ ] **Step 3: `collection_repository.py` — replace 1 call site**

| Line | Before | After |
|---|---|---|
| 59 | `rows = await self.connection.fetch("SELECT * FROM markets.collection_handles")` | `rows = await self.execute_query("SELECT * FROM markets.collection_handles")` |

- [ ] **Step 4: `product_repository.py` — fix `executor: None` bug and replace 1 call site**

Fix `__init__` signature:
```python
# Before:
def __init__(self, connection, executor : None):
# After:
def __init__(self, connection, executor=None):
```

Replace `copy_to_table`:
```python
# Before (lines 17–23):
async def _copy_to_table(self, df, table):
    buf = io.BytesIO()
    df.to_csv(buf, index=False, header=True, encoding='utf-8')
    buf.seek(0)
    await self.connection.copy_to_table(
        table,
        source=buf,
        format='csv',
        header=True)

# After:
async def _copy_to_table(self, df, table):
    buf = io.BytesIO()
    df.to_csv(buf, index=False, header=True, encoding='utf-8')
    buf.seek(0)
    await self.execute_copy_to_table(table, buf, format='csv', header=True)
```

> **Note:** Passing `"pricing.shopify_staging_raw"` as `table_name` (with dotted schema) to asyncpg `copy_to_table` is a pre-existing bug (Improvement I4). Do not fix it here — it's a separate concern.

- [ ] **Step 5: Verify all four files**

```bash
grep -rn "self\.connection\." \
  src/automana/core/repositories/app_integration/shopify/pipeline_repository.py \
  src/automana/core/repositories/app_integration/shopify/market_repository.py \
  src/automana/core/repositories/app_integration/shopify/collection_repository.py \
  src/automana/core/repositories/app_integration/shopify/product_repository.py
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add \
  src/automana/core/repositories/app_integration/shopify/pipeline_repository.py \
  src/automana/core/repositories/app_integration/shopify/market_repository.py \
  src/automana/core/repositories/app_integration/shopify/collection_repository.py \
  src/automana/core/repositories/app_integration/shopify/product_repository.py
git commit -m "refactor(repo): route all Shopify repositories through abstract wrappers; fix executor=None bug"
```

---

## Task 7: `ops/pipeline_health_snapshot_repository.py`

**Files:**
- Modify: `src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py`

- [ ] **Step 1: Apply substitution**

| Line | Before | After |
|---|---|---|
| 94 | `record = await self.connection.fetchrow(_LATEST_SQL, check_set, exclude_run_id)` | `record = await self.execute_fetchrow(_LATEST_SQL, (check_set, exclude_run_id))` |

- [ ] **Step 2: Verify**

```bash
grep -n "self\.connection\." src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py
```

Expected: no output.

- [ ] **Step 3: Final sweep — confirm no concrete repo outside abstract uses self.connection directly**

```bash
grep -rn "self\.connection\." \
  src/automana/core/repositories/ \
  src/automana/api/repositories/ \
  --include="*.py" | grep -v "abstract_repositories"
```

Expected: no output.

- [ ] **Step 4: Run all existing tests**

```bash
cd src && python -m pytest automana/tests/ -v
```

Expected: all tests that passed before still pass.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py
git commit -m "refactor(repo): route PipelineHealthSnapshotRepository through abstract wrappers"
```

---

## Self-Review

**Spec coverage:**
- ✅ All `self.connection.*` calls in 9 concrete repos removed
- ✅ All new primitives wrapped in abstract
- ✅ QueryExecutor gap documented (I1)
- ✅ `ShopifyPipelineRepository.__init__` missing — fixed in Task 6
- ✅ `ProductRepository executor: None` bug — fixed in Task 6
- ✅ `PricingTierRepository.execute_procedure` local override removed in Task 5
- ✅ Behavioral risk (timeout=7200 removal) flagged in Task 5 preamble
- ✅ Pre-existing `MarketRepository.update` indentation bug documented (I5) — not fixed here (out of scope)

**Placeholder scan:** No TBDs or TODOs.

**Type consistency:** `execute_fetchrow(query, values=())` consistent across test and implementation. `execute_copy_to_table(table_name, source, **kwargs)` consistent. `execute_procedure(proc_name, args=(), timeout=None)` consistent.
