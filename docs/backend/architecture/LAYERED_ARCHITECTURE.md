# Layered Architecture

AutoMana follows a strict 4-layer architectural pattern that separates concerns and enforces a one-way dependency direction: **Router → Service → Repository → Database**.

## Overview of Layered Architecture Pattern

The layered architecture pattern organizes the application into horizontal layers, each with a specific responsibility. Each layer only calls the layer immediately below it, never the reverse or sideways. This creates a clear contract between layers and makes the system predictable and testable.

**Why layers matter:**

- **Separation of Concerns**: Each layer has one job (HTTP handling, business logic, data access, persistence)
- **Testability**: Each layer can be tested in isolation by mocking the layers below
- **Maintainability**: Changes in one layer (e.g., switching from PostgreSQL to a different DB) don't cascade to other layers
- **Scalability**: Data access logic is centralized, making it easier to optimize queries or add caching
- **Reusability**: Services can be called from HTTP endpoints, Celery workers, or CLI tools

## Layer 1: Router (HTTP Request Handling)

**Location**: `src/automana/api/routers/`

**Responsibility**: The router layer is the HTTP entry point. It receives requests, validates input, handles authentication, and returns HTTP responses. Routers know about HTTP status codes, request/response serialization, and dependency injection.

**Key characteristics**:
- FastAPI route handlers (decorated with `@router.get()`, `@router.post()`, etc.)
- Input validation via Pydantic schemas
- Dependency injection for `ServiceManager` and `CurrentUser`
- HTTP-specific error handling (400, 401, 403, 404, 500)
- Response wrapping in `ApiResponse` or `PaginatedResponse`

### Example from Codebase

In `src/automana/api/routers/auth.py`:

```python
@router.post("/auth/login", response_model=ApiResponse[UserResponse])
async def login(
    credentials: LoginRequest,
    service_manager: ServiceManagerDep,
) -> ApiResponse[UserResponse]:
    """
    Authenticate user and create a session.
    
    - Input validation: LoginRequest ensures email and password are present
    - Service layer is called to validate credentials
    - Response is wrapped in ApiResponse
    """
    result = await service_manager.execute_service(
        "auth.auth.login",  # Real service key (domain.subdomain.action)
        email=credentials.email,
        password=credentials.password,
    )
    return ApiResponse(data=UserResponse(**result))
```

**Key patterns**:

1. **Dependency Injection**: Routers declare their dependencies as function parameters:
   ```python
   async def my_endpoint(
       service_manager: ServiceManagerDep,  # Singleton ServiceManager
       current_user: CurrentUserDep,        # Authenticated user or None
       page: int = Query(1),                # Pagination
   ) -> ApiResponse[SomeResponse]:
       # ...
   ```

2. **Input Validation**: Pydantic models validate request data:
   ```python
   class LoginRequest(BaseModel):
       email: EmailStr
       password: constr(min_length=8)
   ```

3. **Service Execution**: All business logic is delegated to services:
   ```python
   result = await service_manager.execute_service(
       "auth.login",
       email=credentials.email,
       password=credentials.password,
   )
   ```

4. **Response Wrapping**: Responses are wrapped in standard envelopes:
   ```python
   return ApiResponse(data=user, status="success")
   return PaginatedResponse(items=cards, total=1000, page=1, page_size=20)
   ```

### Error Handling in Routers

Routers catch exceptions from services and convert them to HTTP responses:

```python
from fastapi import HTTPException

@router.get("/card-reference/suggest")
async def suggest_cards(
    service_manager: ServiceManagerDep,
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=20),
):
    """From src/automana/api/routers/mtg/card_reference.py — actual codebase."""
    try:
        result = await service_manager.execute_service(
            "card_catalog.card.suggest",  # Real service key
            query=q,
            limit=limit,
        )
        return ApiResponse(data=result, message="Suggestions retrieved successfully")
    except ValueError as e:
        # Service-level validation error → 400 Bad Request
        raise HTTPException(status_code=400, detail=str(e))
    except AuthenticationError as e:
        # Auth failure → 401 Unauthorized
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except PermissionError as e:
        # Insufficient privileges → 403 Forbidden
        raise HTTPException(status_code=403, detail="Access denied")
    except ResourceNotFoundError as e:
        # Resource doesn't exist → 404 Not Found
        raise HTTPException(status_code=404, detail=str(e))
```

## Layer 2: Service (Business Logic)

**Location**: `src/automana/core/services/` and `src/automana/api/services/`

**Responsibility**: Services contain business logic and orchestration. They decide *what* to do: validate rules, call repositories, transform data, and handle side effects. Services never know about HTTP or database internals.

**Key characteristics**:
- Pure async functions decorated with `@ServiceRegistry.register("service.key")`
- Service function signatures match the parameters provided by routers
- Services accept repositories as function parameters
- Services return plain Python dicts or objects (never FastAPI response types)
- Services handle transactional logic and rollback
- Logging uses structured extra context

### Example from Codebase

In `src/automana/core/services/ops/pricing_report.py`:

```python
@ServiceRegistry.register(
    "ops.integrity.pricing_report",
    db_repositories=["price", "ops"],
)
async def pricing_report(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
) -> dict:
    """
    Run the pricing data-quality report.
    
    Args:
        metrics:  comma-separated string (CLI) or list of metric paths.
        category: filter by category — health, volume, timing, status.
    
    Returns:
        A report dict with check_set, total_checks, errors, warnings, passed, rows.
    """
    return await run_metric_report(
        check_set="pricing_report",
        prefix="pricing.",
        metrics=metrics,
        category=category,
        repositories={
            "price_repository": price_repository,
            "ops_repository": ops_repository,
        },
    )
```

### Service Lifecycle

1. **Service Registration**: At app startup, all services in `SERVICE_MODULES` are imported, and their decorated functions are registered in `ServiceRegistry`.

2. **Service Discovery**: When a router calls `service_manager.execute_service("ops.pricing_report", ...)`:
   - The `ServiceManager` looks up the service key in `ServiceRegistry`
   - It finds the module path, function name, required repositories, and transaction flag
   - It dynamically imports the module and retrieves the function

3. **Repository Instantiation**: The `ServiceManager` creates repositories based on the service's declared needs:
   ```python
   repositories = {}
   for repo_type in service_config.db_repositories:
       repo_info = ServiceRegistry.get_db_repository(repo_type)
       module_path, class_name = repo_info
       repo_class = getattr(importlib.import_module(module_path), class_name)
       repositories[f"{repo_type}_repository"] = repo_class(conn, query_executor)
   ```

4. **Execution**: The service function is called with repositories and request parameters:
   ```python
   result = await service_method(**repositories, **kwargs)
   ```

5. **Response Return**: The service returns a plain dict or object. The router wraps it in the appropriate HTTP response.

### How Services Call Repositories

Services declare repository dependencies as function parameters. The `ServiceManager` injects them:

```python
async def card_search_service(
    card_repository: CardRepository,  # Injected by ServiceManager
    query: str,                       # Passed by router/caller
) -> list[CardResponse]:
    """Search for cards matching a query."""
    
    # Repositories handle the SQL queries
    results = await card_repository.search(query)
    
    # Services apply business logic (filtering, sorting, etc.)
    filtered = [r for r in results if r.price > 0]
    
    return filtered
```

### Service Best Practices

1. **One responsibility per service**: A service should do one thing well.
2. **Declare repositories upfront**: The decorator lists all needed repositories so `ServiceManager` can inject them.
3. **Avoid side effects**: Services should be pure functions (same inputs → same outputs).
4. **Use structured logging**: Log context in `extra={}` dict:
   ```python
   logger.info(
       "card_search_completed",
       extra={
           "query": query,
           "result_count": len(results),
           "duration_ms": duration,
       },
   )
   ```
5. **Let repositories handle SQL**: Don't write SQL in services; delegate to repositories.

## Layer 3: Repository (Data Access)

**Location**: `src/automana/core/repositories/` and `src/automana/api/repositories/`

**Responsibility**: Repositories handle data access. They build SQL queries, execute them, and return raw data. Repositories never contain business logic; they just answer questions like "get me all cards with id in (1,2,3)" or "insert this pricing observation".

**Key characteristics**:
- Classes that extend `AbstractDBRepository` (for DB) or `AbstractAPIRepository` (for external APIs)
- Methods are async and single-purpose (`get_by_id()`, `search()`, `insert()`, `update()`)
- Methods return raw data structures (dicts, lists, objects) without business context
- Query builders can be used to compose complex queries
- Connection is passed in via the constructor (provided by `ServiceManager`)

### Example from Codebase

In `src/automana/core/repositories/ops/ops_repository.py`:

```python
class OpsRepository(AbstractRepository):
    @property
    def name(self):
        return "OpsRepository"
    
    async def insert_batch_step(
        self, 
        batch_step: MTGStockBatchStep
    ):
        """Insert a pipeline batch step record."""
        query = """
        INSERT INTO ops.ingestion_step_batches (
            ingestion_run_step_id,
            batch_seq,
            range_start,
            range_end,
            status,
            items_ok,
            items_failed,
            bytes_processed,
            duration_ms,
            error_code,
            error_details
        )
        SELECT
            st.id,
            $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        FROM ops.ingestion_run_steps st
        WHERE st.ingestion_run_id = $1
        AND st.step_name = $2
        LIMIT 1
        ON CONFLICT (ingestion_run_step_id, batch_seq) DO NOTHING;
        """
        await self.execute_query(query, batch_step.to_tuple())
    
    async def start_run(
        self,
        pipeline_name: str,
        source_name: str,
        run_key: str,
        celery_task_id: str = None,
        notes: str | None = None,
    ) -> int:
        """Start a new pipeline ingestion run and return its ID."""
        query = """
        WITH src AS (
            SELECT id FROM ops.sources WHERE name = $2 LIMIT 1
        ),
        already_started AS (
            SELECT id FROM ops.ingestion_runs
            WHERE source_id = (SELECT id FROM src)
            AND run_key = $3
            AND status IN ('running', 'success')
            LIMIT 1
        )
        INSERT INTO ops.ingestion_runs (
            source_id,
            run_key,
            status,
            celery_task_id,
            notes,
            started_at
        )
        SELECT
            src.id,
            $3,
            'running',
            $4,
            $5,
            NOW()
        WHERE NOT EXISTS (SELECT 1 FROM already_started)
        RETURNING id;
        """
        result = await self.execute_query(query, pipeline_name, source_name, run_key, celery_task_id, notes)
        return result[0][0] if result else None
```

### Query Builder Pattern

For complex queries, repositories can use a query builder to compose conditions dynamically:

```python
class CardRepository(AbstractRepository):
    async def search(
        self,
        name: str | None = None,
        set_code: str | None = None,
        min_price: float | None = None,
        rarity: str | None = None,
    ) -> list[dict]:
        """Search cards by multiple optional criteria."""
        
        query = "SELECT * FROM card_catalog.cards WHERE 1=1"
        params = []
        
        if name:
            query += " AND name ILIKE %s"
            params.append(f"%{name}%")
        
        if set_code:
            query += " AND set_code = %s"
            params.append(set_code)
        
        if min_price is not None:
            query += " AND price >= %s"
            params.append(min_price)
        
        if rarity:
            query += " AND rarity = %s"
            params.append(rarity)
        
        return await self.execute_query(query, *params)
```

### Async Repository Methods

Repositories are async-first. All queries are executed asynchronously to avoid blocking the event loop:

```python
class AsyncRepository(AbstractDBRepository):
    async def execute_query(self, query: str, *args) -> list[tuple]:
        """Execute a query that returns results."""
        return await self.connection.fetch(query, *args)
    
    async def execute_command(self, query: str, *args) -> None:
        """Execute a command that doesn't return results."""
        await self.connection.execute(query, *args)
    
    async def get_by_id(self, table: str, id: int) -> dict | None:
        """Fetch a single row by primary key."""
        query = f"SELECT * FROM {table} WHERE id = $1"
        result = await self.execute_query(query, id)
        return dict(result[0]) if result else None
```

### Repository Best Practices

1. **Single responsibility**: Each method does one data access operation.
2. **Named parameters**: Use parameterized queries to prevent SQL injection:
   ```python
   # GOOD
   await conn.execute("SELECT * FROM users WHERE id = $1", user_id)
   
   # BAD - SQL injection risk!
   query = f"SELECT * FROM users WHERE id = {user_id}"
   ```
3. **Consistent return types**: A method should always return the same structure.
4. **Document the query**: Add comments explaining complex SQL.
5. **Avoid logic**: Repositories return raw data; business logic belongs in services.

## Layer 4: Database (PostgreSQL + TimescaleDB + pgvector)

**Location**: Database server (Postgres or ngrok-tunneled Postgres in dev)

**Responsibility**: The database layer persists data, enforces constraints, and provides atomicity/consistency/isolation/durability (ACID) guarantees.

**Key characteristics**:
- PostgreSQL 14+ with TimescaleDB extension (for hypertables) and pgvector (for embeddings)
- Connection pooling via asyncpg (async) and psycopg2 (sync)
- Transactions managed by `ServiceManager`
- Schema defined in `database/SQL/schemas/`
- Migrations stored in `database/SQL/migrations/`

### Connection Pooling

The `ServiceManager` manages two connection pools:

1. **Async Pool** (asyncpg): Used for most services
   ```python
   async_db_pool = await init_async_pool(settings)
   # The pool creates up to `min_size` connections immediately and up to `max_size` on demand.
   # Connections are reused across requests.
   ```

2. **Sync Pool** (psycopg2): Used for operations requiring synchronous access (rare)
   ```python
   sync_db_pool = await init_sync_pool_with_retry(settings)
   # Used in worker threads where async/await is not available.
   ```

### Transaction Scope

`ServiceManager._execute_service()` wraps services in transactions based on the service's `runs_in_transaction` flag:

```python
# Services with runs_in_transaction=True (most services)
async with self.transaction() as conn:  # BEGIN
    result = await service_method(**repositories, **kwargs)
    # Implicit COMMIT if no exception, ROLLBACK if exception
```

**Transaction context**:

```python
@asynccontextmanager
async def transaction(self):
    """Execute operations in a transaction"""
    connection = None
    try:
        connection = await self.connection_pool.acquire()
        transaction = connection.transaction()
        await transaction.start()  # BEGIN
        try:
            yield connection
            await transaction.commit()  # COMMIT
            logger.debug("Transaction committed")
        except Exception as e:
            await transaction.rollback()  # ROLLBACK
            logger.debug("Transaction rolled back")
            raise
    finally:
        if connection is not None:
            await self.connection_pool.release(connection)
```

**When NOT to use transactions**:

Some services (especially those calling stored procedures with internal transaction control) set `runs_in_transaction=False`:

```python
@ServiceRegistry.register(
    "pricing.load_staging_prices_batched",
    db_repositories=["pricing"],
    runs_in_transaction=False,  # Stored proc manages its own COMMIT/ROLLBACK
)
async def load_staging_prices_batched(pricing_repository, ...):
    # ...
```

### Caching Layer (Redis Integration)

Some services use Redis for caching to reduce database load:

```python
from redis import Redis

@ServiceRegistry.register("cards.get_by_id", db_repositories=["cards"])
async def get_card_by_id(
    cards_repository: CardRepository,
    card_id: int,
    redis_client: Redis,  # Optional caching
) -> dict:
    """Fetch a card, using Redis cache if available."""
    cache_key = f"card:{card_id}"
    
    # Try cache first
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Fetch from database
    card = await cards_repository.get_by_id(card_id)
    
    # Cache for 1 hour
    redis_client.setex(cache_key, 3600, json.dumps(card))
    
    return card
```

## Request Flow Through Layers (HTTP)

Here's the step-by-step flow of a typical HTTP request through all four layers:

```
1. CLIENT REQUEST
   └─ POST /api/cards/search?query=black+lotus

2. ROUTER LAYER (src/automana/api/routers/cards.py)
   ├─ FastAPI receives request
   ├─ Dependency injection provides ServiceManager and CurrentUser
   ├─ Input validation via Pydantic (query parameter type checking)
   └─ Router function is called

3. SERVICE LAYER (src/automana/core/services/cards/search.py)
   ├─ ServiceManager.execute_service("cards.search", query="black lotus", ...)
   ├─ ServiceManager looks up "cards.search" in ServiceRegistry
   ├─ ServiceManager imports module and retrieves the service function
   ├─ ServiceManager instantiates repositories (CardRepository, etc.)
   ├─ Service function is called with repositories and parameters
   ├─ Service applies business logic (filtering, sorting, permissions check)
   └─ Service returns plain dict with results

4. REPOSITORY LAYER (src/automana/core/repositories/cards/card_repository.py)
   ├─ CardRepository.search(query="black lotus")
   ├─ Repository builds parameterized SQL query
   ├─ Repository executes query via connection (asyncpg)
   └─ Repository returns raw data from database

5. DATABASE LAYER (PostgreSQL)
   ├─ Postgres receives query via connection pool
   ├─ Query optimizer decides execution plan
   ├─ Indexes are used for fast lookup
   ├─ Rows are fetched from disk/cache
   └─ Results are returned to repository

6. RESPONSE FLOW (back up the layers)
   ├─ Repository returns data to service
   ├─ Service transforms/filters data if needed
   ├─ Service returns dict to ServiceManager
   ├─ ServiceManager returns result to router
   ├─ Router wraps result in ApiResponse
   └─ FastAPI serializes to JSON and sends to client

7. CLIENT RESPONSE
   └─ HTTP 200 with JSON payload
```

## Transaction Management Strategy

**Principle**: One transaction per request (when `runs_in_transaction=True`).

**Implementation**:

1. **Router calls ServiceManager.execute_service()**
2. **ServiceManager begins transaction** (BEGIN)
3. **Service executes with repositories** (all queries in same transaction)
4. **Service returns result** → implicit COMMIT
5. **If any error occurs** → implicit ROLLBACK

**Nested transactions** are not needed because:
- Each service operates within a single transaction
- Savepoints (Postgres's nested transactions) are used only in exceptional cases
- Complex workflows use Celery pipelines, not nested service calls

**Example transaction flow**:

```python
# Router calls this:
await service_manager.execute_service("cards.create", name="Black Lotus", price=100)

# Inside ServiceManager._execute_service():
async with self.transaction() as conn:  # BEGIN TRANSACTION
    try:
        # Service receives conn in repositories
        result = await card_service(
            card_repository=CardRepository(conn),
            name="Black Lotus",
            price=100,
        )
        # Service returns result
        # Implicit COMMIT here
    except Exception:
        # Implicit ROLLBACK here
        raise

return result
```

## Error Handling Across Layers

Errors flow up the stack, with each layer deciding how to handle them:

```
Database Layer
  └─ Constraint violation (e.g., duplicate key)
     └─ Asyncpg raises ProgrammingError / IntegrityError

Repository Layer
  └─ Catches Asyncpg exception
  └─ Either:
     a) Translates to custom exception (CardNotFoundError)
     b) Re-raises as ValueError for caller to decide

Service Layer
  └─ Catches Repository exceptions
  └─ Either:
     a) Handles (logs, retries, proceeds with default)
     b) Raises custom service exception (InsufficientInventoryError)

Router Layer
  └─ Catches Service exceptions
  └─ Converts to HTTP response:
     - ValueError → 400 Bad Request
     - PermissionError → 403 Forbidden
     - ResourceNotFoundError → 404 Not Found
     - Exception → 500 Internal Server Error
```

**Example error handling**:

```python
# Database constraint prevents duplicate emails
async def register_user(user_repository, email, password):
    try:
        # Repo may raise asyncpg.IntegrityError if email already exists
        user_id = await user_repository.create(email, password)
        return {"id": user_id, "email": email}
    except asyncpg.IntegrityError:
        # Service catches and translates to domain error
        raise ValueError(f"Email {email} already registered")

# Router catches and converts to HTTP response
@router.post("/users/register")
async def register(req: RegisterRequest, service_manager: ServiceManagerDep):
    try:
        result = await service_manager.execute_service(
            "auth.register",
            email=req.email,
            password=req.password,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        # Service ValueError → 400 Bad Request
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected error → 500 Internal Server Error
        logger.exception("unexpected_error", extra={"endpoint": "register"})
        raise HTTPException(status_code=500, detail="Internal server error")
```

## Testing Each Layer in Isolation

Each layer can be tested independently by mocking the layers below:

### Testing Routers (mock services)

```python
# tests/unit/api/routers/test_auth.py

async def test_login_success(client: TestClient):
    """Test router layer with mocked service."""
    # Arrange: Mock the service manager
    mock_service = AsyncMock(return_value={"id": 1, "email": "test@example.com"})
    
    with patch.object(ServiceManager, "execute_service", mock_service):
        # Act: Call the endpoint
        response = client.post("/api/auth/login", json={"email": "test@example.com", "password": "123456"})
        
        # Assert: Check HTTP response
        assert response.status_code == 200
        assert response.json()["data"]["email"] == "test@example.com"
```

### Testing Services (mock repositories)

```python
# tests/unit/core/services/test_card_search.py

async def test_card_search_filters_by_price(mocker):
    """Test service logic with mocked repository."""
    # Arrange: Create mock repository
    mock_repo = AsyncMock()
    mock_repo.search = AsyncMock(return_value=[
        {"id": 1, "name": "Black Lotus", "price": 500},
        {"id": 2, "name": "Common Card", "price": 0.10},
    ])
    
    # Act: Call service
    result = await card_search_service(
        card_repository=mock_repo,
        min_price=1.0,
    )
    
    # Assert: Service filters out cheap cards
    assert len(result) == 1
    assert result[0]["price"] == 500
```

### Testing Repositories (integration test with real DB)

```python
# tests/integration/repositories/test_card_repository.py

async def test_create_card(async_db_connection):
    """Test repository with real database."""
    # Arrange: Create repository with real connection
    repo = CardRepository(async_db_connection)
    
    # Act: Create card
    card_id = await repo.create(name="Black Lotus", set_code="LTD")
    
    # Assert: Card is in database
    card = await repo.get_by_id(card_id)
    assert card["name"] == "Black Lotus"
```

## Performance Implications of Layering

Layering has performance costs, but the benefits (maintainability, testability) outweigh the costs:

| Cost | Mitigation |
|------|-----------|
| Extra function calls | Negligible (ns scale) |
| N+1 query problems | Services batch loads in repositories |
| Lack of query optimization | Repositories can use SQL window functions, CTEs, etc. |
| Serialization overhead | JSON serialization is minimal compared to network latency |

**Performance best practices**:

1. **Batch queries**: Instead of loading one card per request, load them all:
   ```python
   # Bad: N+1 queries (N separate trips to DB)
   for card_id in [1, 2, 3]:
       card = await repository.get_by_id(card_id)
   
   # Good: One query
   cards = await repository.get_by_ids([1, 2, 3])
   ```

2. **Use database aggregations**: Let PostgreSQL do the math:
   ```python
   # Bad: Load all rows and count in Python
   all_cards = await repository.get_all()
   count = len(all_cards)
   
   # Good: Count in database
   count = await repository.count()
   ```

3. **Index heavily used queries**: The DBA team maintains indexes on all frequently-queried columns.

4. **Use SELECT projections**: Only fetch columns you need:
   ```python
   # Bad: SELECT * (all columns)
   query = "SELECT * FROM cards WHERE name ILIKE $1"
   
   # Good: Specific columns
   query = "SELECT id, name, price FROM cards WHERE name ILIKE $1"
   ```

## Common Pitfalls and How to Avoid Them

### Pitfall 1: Business Logic in Routers

**Problem**: Logic that should be in services leaks into routers.

```python
# BAD: Router doing business logic
@router.post("/cards/batch-import")
async def batch_import(file: UploadFile, service_manager: ServiceManagerDep):
    content = await file.read()
    cards = parse_csv(content)  # ← Business logic in router!
    
    for card in cards:
        await service_manager.execute_service("cards.create", **card)
```

**Solution**: Move logic to service.

```python
# GOOD: Service handles logic
@router.post("/cards/batch-import")
async def batch_import(file: UploadFile, service_manager: ServiceManagerDep):
    content = await file.read()
    result = await service_manager.execute_service(
        "cards.import_from_csv",
        csv_content=content,
    )
    return ApiResponse(data=result)

# Service does the work
@ServiceRegistry.register("cards.import_from_csv", db_repositories=["cards"])
async def import_from_csv(cards_repository, csv_content: str):
    cards = parse_csv(csv_content)
    result = {"imported": 0, "errors": []}
    for card in cards:
        try:
            await cards_repository.create(**card)
            result["imported"] += 1
        except Exception as e:
            result["errors"].append(str(e))
    return result
```

### Pitfall 2: SQL in Services

**Problem**: SQL queries written in service functions instead of repositories.

```python
# BAD: SQL in service
@ServiceRegistry.register("cards.expensive_search")
async def expensive_search(db_connection, query: str):
    result = await db_connection.fetch(
        f"SELECT * FROM cards WHERE name ILIKE '%{query}%'"  # ← SQL in service!
    )
    return result
```

**Solution**: Move SQL to repository.

```python
# GOOD: Repository handles SQL
@ServiceRegistry.register("cards.expensive_search", db_repositories=["cards"])
async def expensive_search(cards_repository, query: str):
    return await cards_repository.search_by_name(query)

class CardRepository(AbstractRepository):
    async def search_by_name(self, query: str):
        sql = "SELECT * FROM card_catalog.cards WHERE name ILIKE $1"
        return await self.execute_query(sql, f"%{query}%")
```

### Pitfall 3: Bypassing ServiceManager

**Problem**: Accessing repositories directly instead of through ServiceManager.

```python
# BAD: Direct repository access
from automana.core.repositories.cards import CardRepository

async def my_endpoint():
    conn = get_db_connection()
    repo = CardRepository(conn)
    cards = await repo.search(...)  # ← No logging context, no timeout, no transaction management!
```

**Solution**: Always use ServiceManager.

```python
# GOOD: ServiceManager handles everything
async def my_endpoint(service_manager: ServiceManagerDep):
    result = await service_manager.execute_service("cards.search", query="...")
    # ServiceManager ensures:
    # - Logging context is set
    # - Command timeout is applied
    # - Transaction is managed
    # - Connection is returned to pool
```

### Pitfall 4: Implicit Dependencies

**Problem**: Services don't declare their repository dependencies upfront.

```python
# BAD: Hidden dependency on OpsRepository
@ServiceRegistry.register("cards.search")  # ← Missing db_repositories!
async def search(cards_repository, query: str):
    # ... service code ...
    
    # Later in the function:
    ops_repo = OpsRepository(???)  # ← Where does connection come from?
    await ops_repo.log_search(query)
```

**Solution**: Declare all dependencies in the decorator.

```python
# GOOD: All dependencies declared
@ServiceRegistry.register(
    "cards.search",
    db_repositories=["cards", "ops"],  # ← ServiceManager injects both
)
async def search(cards_repository, ops_repository, query: str):
    results = await cards_repository.search(query)
    await ops_repository.log_search(query)
    return results
```

## See Also

- [`docs/DESIGN_PATTERNS.md`](../DESIGN_PATTERNS.md) — Design patterns used throughout the codebase
- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) — High-level architecture overview
- [`docs/ARCHITECTURE_MASTER.md`](../../ARCHITECTURE_MASTER.md) — Full architecture index
- [`SERVICE_DISCOVERY.md`](SERVICE_DISCOVERY.md) — How services are discovered and instantiated
- [`REQUEST_FLOWS.md`](REQUEST_FLOWS.md) — Detailed request flow through the system
