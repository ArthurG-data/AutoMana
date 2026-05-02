# Repository Pattern

This document explains how the repository pattern is implemented in AutoMana, including CRUD operations, async/sync design, transaction handling, testing strategies, and performance considerations.

**Key Files:**
- Abstract base: [`src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`](../../../src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py)
- Concrete repos: [`src/automana/core/repositories/`](../../../src/automana/core/repositories/)

---

## Table of Contents

1. [Repository Responsibilities](#repository-responsibilities)
2. [Abstract Repository Base Class](#abstract-repository-base-class)
3. [Query Builder Patterns](#query-builder-patterns)
4. [CRUD Operations](#crud-operations)
5. [Async vs. Sync Repositories](#async-vs-sync-repositories)
6. [Transaction Scope](#transaction-scope)
7. [Error Handling](#error-handling)
8. [Performance Considerations](#performance-considerations)
9. [Testing Repositories](#testing-repositories)

---

## Repository Responsibilities

A repository is responsible for:

1. **Data Access Abstraction**: Hide SQL queries and connection details from service layer
2. **Query Construction**: Build parameterized SQL queries safely (no string concatenation)
3. **Result Mapping**: Convert raw database rows to domain objects or dictionaries
4. **Error Translation**: Convert database-level errors to application exceptions
5. **Connection Management**: Use injected connection (async or sync, pool-managed)

**Architectural Invariant:** Repositories are the *only* place where SQL queries appear in the codebase. No service, router, or Celery task should execute raw SQL.

---

## Abstract Repository Base Class

### Definition

**File:** [`AbstractDBRepository.py`](../../../src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py)

```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, Union
import asyncpg, psycopg2

T = TypeVar('T')

class AbstractRepository(Generic[T], ABC):
    """
    Generic base class for all database repositories.
    
    Supports both async (asyncpg) and sync (psycopg2) connections
    via a pluggable QueryExecutor.
    """
    
    def __init__(self, connection: Union[asyncpg.Connection, psycopg2.extensions.connection],
                 executor: QueryExecutor = None):
        self.connection = connection
        self.executor = executor
        self._thread_pool = ThreadPoolExecutor(max_workers=4)
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the entity this repository manages."""
        pass
    
    # Async methods (preferred)
    async def execute_query(self, query: str, *args) -> list:
        """Execute SELECT; return rows."""
        if self.executor:
            return await self.executor.execute_query(self.connection, query, *args)
        else:
            return await self.connection.fetch(query, *args)
    
    async def execute_command(self, query, *args):
        """Execute INSERT/UPDATE/DELETE; no return."""
        if self.executor:
            return await self.executor.execute_command(self.connection, query, *args)
        else:
            return await self.connection.execute(query, *args)
    
    # Sync methods (fallback)
    def execute_query_sync(self, query, *args) -> list:
        """Sync version of execute_query."""
        if self.executor:
            return self.executor.execute_query(self.connection, query, *args)
        else:
            with self.connection.cursor() as cursor:
                cursor.execute(query, args)
                return cursor.fetchall()
    
    def execute_command_sync(self, query, *args):
        """Sync version of execute_command."""
        if self.executor:
            return self.executor.execute_command(self.connection, query, *args)
        else:
            with self.connection.cursor() as cursor:
                cursor.execute(query, args)
                self.connection.commit()
    
    # Abstract CRUD methods (all subclasses must implement)
    @abstractmethod
    async def add(self, item: T) -> None:
        pass
    
    @abstractmethod
    async def get(self, id) -> Optional[T]:
        pass
    
    @abstractmethod
    async def update(self, item: T) -> None:
        pass
    
    @abstractmethod
    async def delete(self, id) -> None:
        pass
    
    @abstractmethod
    async def list(self, items: T) -> list[T]:
        pass
```

### Design Decisions

**Why QueryExecutor?**
- Separates SQL execution from connection management
- Allows swapping implementations (e.g., mock executor for testing)
- Centralizes error mapping (database errors → application exceptions)

**Why both async and sync?**
- FastAPI handlers are async; they use async repositories with asyncpg
- Celery tasks are sync-by-default; they use sync repositories with psycopg2
- Both paths share the same repository classes via optional executor injection

**Why ThreadPoolExecutor?**
- Provides a fallback for blocking I/O when executor is unavailable
- Max 4 workers prevents thread pool exhaustion

---

## Query Builder Patterns

### Safe Parameterized Queries

**Never use string concatenation or f-strings for SQL variables.** Always use parameterized queries with `$1`, `$2`, ... placeholders.

#### ✓ CORRECT: Parameterized

```python
async def get_by_scryfall_id(self, scryfall_id: str) -> Optional[dict]:
    sql = """
        SELECT cv.card_version_id, uc.card_name, s.set_code
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_version cv ON cv.card_version_id = cei.card_version_id
        JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
        JOIN card_catalog.sets s ON s.set_id = cv.set_id
        WHERE cei.card_identifier_ref_id = 1 AND cei.value = $1
    """
    rows = await self.execute_query(sql, (scryfall_id,))
    return dict(rows[0]) if rows else None
```

**Key points:**
- `$1` is a named placeholder for the first argument
- Arguments are passed as a tuple: `(scryfall_id,)`
- Arguments automatically escaped by asyncpg/psycopg2

#### ✗ WRONG: String concatenation (SQL injection vulnerability)

```python
# NEVER do this:
sql = f"SELECT * FROM card_version WHERE set_code = '{set_code}'"
rows = await self.connection.fetch(sql)
```

### Dynamic Placeholder Generation

For variable-length argument lists (e.g., `IN (...)` clauses), generate placeholders dynamically:

```python
async def get_many(self, user_id: UUID, collection_ids: list[UUID]):
    # Generate $2, $3, $4, ... for each collection_id
    placeholders = ', '.join(f'${i + 2}' for i in range(len(collection_ids)))
    
    query = f"""
        SELECT c.collection_id, c.collection_name, c.description
        FROM user_collection.collections c
        WHERE c.user_id = $1 AND c.collection_id IN ({placeholders})
    """
    
    # Pass user_id first, then all collection_ids
    values = (user_id, *collection_ids)
    return await self.execute_query(query, values)
```

**Safe pattern:**
- Placeholder positions are hardcoded ($1, $2, $3, ...)
- Argument list length matches placeholder count
- Values tuple includes all arguments in the correct order

### CTE and Subquery Patterns

For complex multi-step queries, use CTEs (WITH clauses) or subqueries:

```python
async def search_cards(self, name_query: str, rarity: str = None, set_code: str = None):
    query = """
        WITH filtered_cards AS (
            SELECT cv.card_version_id, uc.card_name, s.set_code, cv.rarity_name
            FROM card_catalog.card_version cv
            JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            WHERE uc.card_name ILIKE $1
        )
        SELECT * FROM filtered_cards
        WHERE ($2::VARCHAR IS NULL OR rarity_name = $2)
          AND ($3::VARCHAR IS NULL OR set_code = $3)
        LIMIT 50
    """
    
    return await self.execute_query(query, (f"%{name_query}%", rarity, set_code))
```

**Pattern:**
- Build the query with placeholders
- Optional filters use `($2 IS NULL OR column = $2)` syntax
- Cleaner than building SQL strings conditionally

---

## CRUD Operations

### Create (INSERT)

#### Single Row

```python
async def add(self, collection_name: str, description: str, user_id: UUID) -> Optional[dict]:
    query = """
        INSERT INTO user_collection.collections 
            (collection_name, description, user_id)
        VALUES ($1, $2, $3)
        RETURNING collection_id, collection_name, description, user_id, created_at, is_active
    """
    result = await self.execute_query(query, (collection_name, description, user_id))
    return dict(result[0]) if result else None
```

**Pattern:**
- INSERT ... VALUES (...)
- RETURNING clause captures generated IDs and timestamps
- Result converted to dict for API serialization

#### Batch Insert

For bulk card imports, use a PL/pgSQL stored procedure:

```python
async def add_many(self, values: list[dict]):
    # Pass JSON array to stored procedure
    import json
    json_payload = json.dumps(values)
    
    query = """
        SELECT * FROM card_catalog.insert_batch_card_versions($1::JSONB)
    """
    result = await self.execute_query(query, (json_payload,))
    
    # Parse JSONB response
    if result:
        return result[0]
    return None
```

**Why stored procedures for batch operations?**
- Single round-trip to database (vs. many individual INSERTs)
- Transaction boundary at server (all-or-nothing semantics)
- Stored procedure handles validation, deduplication, error collection
- Returns detailed error report (which rows failed and why)

#### Batch Insert Response

```python
@dataclass
class BatchInsertResponse:
    total_processed: int
    successful_inserts: int
    failed_inserts: int
    success_rate: float
    inserted_card_ids: list[UUID]
    errors: list[str]
```

### Read (SELECT)

#### Single Row by ID

```python
async def get(self, card_version_id: UUID) -> Optional[dict]:
    query = """
        SELECT cv.card_version_id, uc.card_name, s.set_code, cv.collector_number
        FROM card_catalog.card_version cv
        JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
        JOIN card_catalog.sets s ON s.set_id = cv.set_id
        WHERE cv.card_version_id = $1
    """
    rows = await self.execute_query(query, (card_version_id,))
    return dict(rows[0]) if rows else None
```

**Pattern:**
- JOINs to fetch related data in one query (avoid N+1 problem)
- Return dict or None (falsy check works naturally)

#### List with Pagination

```python
async def list_by_user(self, user_id: UUID, limit: int = 50, offset: int = 0) -> list[dict]:
    query = """
        SELECT c.collection_id, c.collection_name, c.description, c.created_at, c.is_active
        FROM user_collection.collections c
        WHERE c.user_id = $1 AND c.is_active = TRUE
        ORDER BY c.created_at DESC
        LIMIT $2 OFFSET $3
    """
    rows = await self.execute_query(query, (user_id, limit, offset))
    return [dict(r) for r in rows]
```

**Pattern:**
- LIMIT/OFFSET for pagination
- ORDER BY to ensure consistent results
- Soft-delete check (is_active = TRUE)

#### Full-Text Search

```python
async def search(self, query: str, limit: int = 10) -> list[dict]:
    sql = """
        SELECT v.card_version_id, v.card_name, v.set_code, v.rarity_name,
               word_similarity($1, v.card_name) AS score
        FROM card_catalog.v_card_name_suggest v
        WHERE $1 % v.card_name  -- trigram match operator
        ORDER BY score DESC
        LIMIT $2
    """
    rows = await self.execute_query(sql, (query, limit))
    return [dict(r) for r in rows]
```

**Pattern:**
- Uses PostgreSQL `pg_trgm` extension (trigram similarity)
- `%` operator checks if text is similar
- `word_similarity()` function scores the match
- Fast string search without full-text indexes

### Update (UPDATE)

#### Partial Update

```python
async def update(self, update_fields: dict, collection_id: UUID, user_id: UUID):
    # Build SET clause dynamically
    counter = 1
    set_clause = ", ".join(
        f"{k} = ${counter + i}"
        for i, k in enumerate(update_fields.keys())
    )
    
    query = f"""
        UPDATE user_collection.collections
        SET {set_clause}
        WHERE collection_id = ${counter + len(update_fields)}
          AND user_id = ${counter + len(update_fields) + 1}
    """
    
    values = (*update_fields.values(), collection_id, user_id)
    await self.execute_command(query, values)
```

**Pattern:**
- Dynamic column lists from dict keys
- Placeholder positions adjusted manually
- WHERE clause ensures ownership guard (only owner can update)

**Better Pattern (stored procedure):**
```python
async def update(self, update_fields: dict, collection_id: UUID, user_id: UUID):
    import json
    
    query = """
        SELECT user_collection.update_collection_by_user($1, $2, $3::JSONB)
    """
    
    await self.execute_command(
        query,
        (collection_id, user_id, json.dumps(update_fields))
    )
```

This offloads validation to the database.

### Delete (DELETE / Soft Delete)

#### Hard Delete (permanent removal)

```python
async def delete(self, card_version_id: UUID):
    query = """
        DELETE FROM card_catalog.card_version
        WHERE card_version_id = $1
        RETURNING card_version_id
    """
    rows = await self.execute_query(query, (card_version_id,))
    return len(rows) > 0
```

#### Soft Delete (logical delete)

```python
async def delete(self, collection_id: UUID, user_id: UUID):
    query = """
        UPDATE user_collection.collections
        SET is_active = FALSE
        WHERE collection_id = $1 AND user_id = $2
    """
    await self.execute_command(query, (collection_id, user_id))
```

**Pattern:**
- Soft delete is safer (reversible, preserves history)
- All SELECTs must include `WHERE is_active = TRUE` filter
- Hard delete used only for truly ephemeral data (session tokens, temp files)

---

## Async vs. Sync Repositories

### Async Repositories (asyncpg)

**Used by:** FastAPI request handlers, async Celery tasks

```python
class CardRepository(AbstractRepository):
    async def get(self, card_id: UUID) -> Optional[dict]:
        rows = await self.execute_query(sql, (card_id,))
        return dict(rows[0]) if rows else None
    
    async def search(self, name: str, limit: int = 50) -> list[dict]:
        rows = await self.execute_query(sql, (f"%{name}%", limit))
        return [dict(r) for r in rows]
```

**Advantages:**
- Non-blocking I/O (FastAPI can handle many concurrent requests)
- No thread pool required
- Native to Python async/await syntax

### Sync Repositories (psycopg2)

**Used by:** CLI, TUI, synchronous Celery tasks (default)

```python
class CardRepository(AbstractRepository):
    def get(self, card_id: UUID) -> Optional[dict]:
        rows = self.execute_query_sync(sql, (card_id,))
        return dict(rows[0]) if rows else None
```

**Advantages:**
- Simpler code (no await keywords)
- Blocks are acceptable in worker processes (no concurrent requests)
- Compatible with blocking libraries (requests, pandas)

### Mixed Usage

A service can accept both async and sync repositories via dependency injection:

```python
@ServiceRegistry.register("card.search", db_repositories=["card"])
async def search_cards(card_repository, name: str) -> list[dict]:
    # card_repository is automatically injected as async (in FastAPI)
    # or sync (in Celery) based on context
    
    if hasattr(card_repository, 'search'):  # async method
        return await card_repository.search(name)
    else:  # sync method (fallback)
        return card_repository.search(name)
```

---

## Transaction Scope

### Explicit Transactions (ServiceManager)

The `ServiceManager` wraps service calls in a transaction:

```python
async def _execute_service(self, service_path, **kwargs):
    async with self.async_pool.acquire() as connection:
        async with connection.transaction():  # Explicit transaction
            # Instantiate repositories with this connection
            repository = CardRepository(connection)
            
            # Call service
            result = await service(repository, **kwargs)
            
            # Transaction commits on __exit__
            # Rollback on exception
            return result
```

**Behavior:**
- All database operations in the service execute within a single transaction
- Either all succeed and commit, or all rollback on exception
- No nested transactions (PostgreSQL uses SAVEPOINTs internally)

### Per-Repository Transactions

For finer control, repositories can start their own transactions:

```python
async def batch_insert(self, card_data: list[dict]):
    async with self.connection.transaction():  # Explicit SAVEPOINT
        for item in card_data:
            await self.execute_command(insert_query, (item,))
    # Commits on __exit__
```

### AutoCommit Mode (Discouraged)

```python
# Connection created with autocommit=True
connection = await asyncpg.connect(..., command_timeout=60)
```

**Drawback:** Each statement commits immediately; no rollback on later errors.

**Best Practice:** Use explicit transactions. Easier to reason about consistency.

---

## Error Handling

### Exception Hierarchy

**File:** [`core/exceptions/repository_layer_exceptions/`](../../../src/automana/core/exceptions/repository_layer_exceptions/)

```python
class RepositoryException(Exception):
    """Base for all repository errors."""
    pass

class DuplicateKeyError(RepositoryException):
    """Unique constraint violation."""
    pass

class ForeignKeyError(RepositoryException):
    """Foreign key constraint violation."""
    pass

class NotFoundError(RepositoryException):
    """Row not found."""
    pass

class TransactionError(RepositoryException):
    """Transaction rollback or deadlock."""
    pass
```

### Error Handling (Try/Catch Pattern)

Database exceptions (from asyncpg) are handled by catching their types directly:

```python
try:
    await self.execute_command(insert_query, values)
except asyncpg.UniqueViolationError as e:
    raise DuplicateKeyError(f"Card already exists: {e}")
except asyncpg.ForeignKeyViolationError as e:
    raise ForeignKeyError(f"Invalid reference: {e}")
except asyncpg.DeadlockDetectedError as e:
    raise TransactionError("Deadlock detected; retry transaction")
except asyncpg.PostgresError as e:
    raise RepositoryException(f"Database error: {e}")
```

**Key asyncpg exception types:**
- `asyncpg.UniqueViolationError` — constraint violation (integrity_constraint_violation in SQLSTATE)
- `asyncpg.ForeignKeyViolationError` — foreign key constraint violation
- `asyncpg.DeadlockDetectedError` — concurrent transaction conflict
- `asyncpg.PostgresError` — base class for all database errors

**Sync (psycopg2) equivalents:**
```python
import psycopg2.errors as pg_errors

try:
    cursor.execute(insert_query, values)
    connection.commit()
except pg_errors.UniqueViolation as e:
    raise DuplicateKeyError(f"Card already exists: {e}")
except pg_errors.ForeignKeyViolation as e:
    raise ForeignKeyError(f"Invalid reference: {e}")
except psycopg2.DatabaseError as e:
    raise RepositoryException(f"Database error: {e}")
```

### Service-Layer Handling

```python
@ServiceRegistry.register("card.add", db_repositories=["card"])
async def add_card(card_repository, card_data: dict) -> dict:
    try:
        result = await card_repository.add(**card_data)
        return {"success": True, "card_id": result}
    except DuplicateKeyError:
        raise ServiceLayerException(
            "Card already exists",
            error_code="DUPLICATE_CARD"
        )
    except ForeignKeyError:
        raise ServiceLayerException(
            "Invalid set or artist reference",
            error_code="INVALID_REFERENCE"
        )
```

---

## Performance Considerations

### N+1 Query Problem

**❌ WRONG:**
```python
async def get_cards_in_set(self, set_id: int):
    # 1 query for cards
    cards = await self.execute_query(
        "SELECT * FROM card_version WHERE set_id = $1",
        (set_id,)
    )
    
    # N queries for artists (one per card)
    for card in cards:
        artist = await self.execute_query(
            "SELECT * FROM artists_ref WHERE artist_id = $1",
            (card['illustration_artist'],)
        )
        card['artist'] = artist
    
    return cards  # 1 + N queries total
```

**✓ CORRECT (single JOIN):**
```python
async def get_cards_in_set(self, set_id: int):
    query = """
        SELECT cv.*, ar.artist_name
        FROM card_catalog.card_version cv
        LEFT JOIN card_catalog.artists_ref ar
          ON ar.artist_id = cv.illustration_artist
        WHERE cv.set_id = $1
    """
    rows = await self.execute_query(query, (set_id,))
    return [dict(r) for r in rows]  # 1 query total
```

### Batch Operations

**❌ WRONG (many round-trips):**
```python
async def add_many_cards(self, card_list: list[dict]):
    results = []
    for card in card_list:
        result = await self.execute_query(insert_query, (card,))
        results.append(result)
    return results  # N round-trips
```

**✓ CORRECT (single stored procedure):**
```python
async def add_many_cards(self, card_list: list[dict]):
    import json
    query = "SELECT * FROM card_catalog.insert_batch_card_versions($1::JSONB)"
    result = await self.execute_query(query, (json.dumps(card_list),))
    return result[0]  # 1 round-trip
```

### Index-Aware Queries

**Bad index usage:**
```python
# Scans entire table
query = "SELECT * FROM card_version WHERE rarity_name = $1"
```

**Good index usage:**
```python
# Uses idx_card_version_rarity
query = """
    SELECT * FROM card_catalog.card_version
    WHERE rarity_id = (SELECT rarity_id FROM card_catalog.rarities_ref WHERE rarity_name = $1)
"""
```

**Explain plan (check it):**
```sql
EXPLAIN ANALYZE
SELECT * FROM card_version WHERE rarity_id = $1;
```

### Connection Pooling

Repositories should never create connections directly. Always use injected pool:

```python
# ✓ Correct: Connection from pool
repository = CardRepository(pooled_connection)

# ✗ Wrong: Creating raw connection
connection = await asyncpg.connect(...)
repository = CardRepository(connection)
```

**Benefits of pooling:**
- Reuse connections (avoid handshake overhead)
- Limit total connection count (prevent resource exhaustion)
- Health checks (evict stale connections)

---

## Testing Repositories

### Unit Tests (Mocked Repository)

```python
# tests/unit/repositories/test_card_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.card_catalog import CardRepository

@pytest.fixture
def mock_connection():
    connection = AsyncMock()
    return connection

@pytest.mark.asyncio
async def test_get_card_by_id(mock_connection):
    # Mock response
    mock_connection.fetch.return_value = [
        {
            'card_version_id': UUID('...'),
            'card_name': 'Black Lotus',
            'set_code': 'LEA'
        }
    ]
    
    repo = CardRepository(mock_connection)
    result = await repo.get(UUID('...'))
    
    assert result['card_name'] == 'Black Lotus'
    mock_connection.fetch.assert_called_once()
```

### Integration Tests (Real Database)

```python
# tests/integration/repositories/test_card_repository.py
import pytest
import asyncpg
from automana.core.repositories.card_catalog import CardRepository

@pytest.fixture
async def db_connection(test_db_url):
    connection = await asyncpg.connect(test_db_url)
    yield connection
    await connection.close()

@pytest.mark.asyncio
async def test_get_card_by_id_integration(db_connection):
    repo = CardRepository(db_connection)
    
    # Seed test data
    card_id = await db_connection.fetchval("""
        INSERT INTO card_catalog.unique_cards_ref (card_name)
        VALUES ('Test Card')
        RETURNING unique_card_id
    """)
    
    # Test repository method
    result = await repo.get(card_id)
    
    assert result['card_name'] == 'Test Card'
    
    # Cleanup
    await db_connection.execute(
        "DELETE FROM card_catalog.unique_cards_ref WHERE unique_card_id = $1",
        card_id
    )
```

### Fixtures (Database State)

```python
@pytest.fixture
def card_factory(db_connection):
    """Factory for creating test cards."""
    async def create(name: str = "Test Card", set_id: int = 1):
        return await db_connection.fetchrow("""
            INSERT INTO card_catalog.card_version
                (unique_card_id, set_id, rarity_id, oracle_text)
            VALUES (
                (SELECT unique_card_id FROM card_catalog.unique_cards_ref WHERE card_name = $1),
                $2,
                (SELECT rarity_id FROM card_catalog.rarities_ref WHERE rarity_name = 'Common'),
                'Test card'
            )
            RETURNING *
        """, name, set_id)
    
    return create
```

---

## See Also

- [`docs/DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) — Table definitions and indexing
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — Layered architecture and service discovery
- [`docs/DESIGN_PATTERNS.md`](../DESIGN_PATTERNS.md) — Repository pattern details (Pattern #4)
- [`src/automana/core/repositories/`](../../../src/automana/core/repositories/) — Concrete implementations
