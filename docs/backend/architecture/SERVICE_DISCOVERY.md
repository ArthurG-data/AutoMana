# Service Discovery and Management

The AutoMana backend uses a sophisticated service discovery pattern called **ServiceManager** to decouple services from their instantiation, dependencies, and lifecycle management. This document explains how services are registered, discovered, and executed.

## ServiceManager Architecture Overview

**ServiceManager** is a singleton that acts as a service registry and factory. It:

1. **Discovers** all available services at startup (via `ServiceRegistry`)
2. **Instantiates** repositories based on service declarations
3. **Manages** transaction context and timeout behavior per-service
4. **Executes** service functions with dependency injection
5. **Handles** connection acquisition and cleanup

**Location**: `src/automana/core/service_manager.py`

### Singleton Pattern

`ServiceManager` is implemented as a singleton to ensure only one instance exists across the application:

```python
class ServiceManager:
    """Singleton class to manage services and their dependencies"""
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ServiceManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
```

**Benefits**:
- Services can be discovered once and reused
- Database connection pools are shared
- Logging context is centralized

### Initialization at Startup

In `src/automana/api/main.py`, the app's lifespan context manager initializes `ServiceManager`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings = get_settings()
        from automana.core.database import init_async_pool
        from automana.core.service_manager import ServiceManager
        
        app.state.async_db_pool = await init_async_pool(settings)
        
        # Initialize ServiceManager singleton
        app.state.service_manager = await ServiceManager.initialize(
            connection_pool=app.state.async_db_pool,
            query_executor=app.state.query_executor,
        )
        yield
    finally:
        await ServiceManager.close()
```

## Service Registration Pattern

Services are registered using the `@ServiceRegistry.register()` decorator. This decorator stores metadata about the service (module, function name, required repositories, etc.) in the `ServiceRegistry`.

### Decorator Syntax

```python
@ServiceRegistry.register(
    "service.key.path",
    db_repositories=["cards", "ops"],      # DB repositories to inject
    api_repositories=["scryfall"],          # API repositories to inject
    runs_in_transaction=True,               # Wrap in transaction
    command_timeout=30.0,                   # Query timeout in seconds
)
async def my_service_function(
    cards_repository: CardRepository,       # Injected by ServiceManager
    ops_repository: OpsRepository,          # Injected by ServiceManager
    scryfall_repository: ScryfallRepository, # Injected by ServiceManager
    param1: str,                            # Passed by caller
    param2: int = 100,                      # Optional parameter
) -> dict:
    """Service docstring."""
    # Implementation
    return {"result": "data"}
```

### Service Key Naming Convention

Service keys follow a hierarchical naming pattern: `"domain.subdomain.action"` or `"domain.action"`

**Examples**:
- `"cards.search"` — Search for cards
- `"cards.import_from_csv"` — Import cards from CSV
- `"auth.login"` — Authenticate user
- `"auth.register"` — Register new user
- `"ops.integrity.scryfall_integrity"` — Run Scryfall integrity checks
- `"pricing.load_staging_prices_batched"` — Load pricing data

**Why hierarchical?**
- Logical organization by domain
- Easy to list services by domain in CLI tools
- Prevents name collisions

## Dependency Injection Mechanics

When a service is executed, `ServiceManager._execute_service()` performs the following steps:

### Step 1: Service Lookup

```python
service_config = ServiceRegistry.get("cards.search")
if not service_config:
    raise ValueError(f"Service not found: cards.search")
```

`ServiceRegistry.get()` returns a `ServiceConfig` object with metadata:

```python
@dataclass
class ServiceConfig:
    module: str              # e.g., "automana.core.services.cards.search"
    function: str            # e.g., "search_service"
    db_repositories: list    # ["cards", "pricing"]
    api_repositories: list   # ["scryfall"]
    runs_in_transaction: bool  # True
    command_timeout: float   # 30.0
    storage_services: list   # ["mtgstock_raw"]
```

### Step 2: Module Import

```python
module = importlib.import_module(service_config.module)
service_method = getattr(module, service_config.function)
```

The module is dynamically imported and the function is retrieved.

### Step 3: Repository Instantiation

Repositories are created based on service declarations:

```python
repositories = {}

# Create DB repositories
for repo_type in service_config.db_repositories:
    repo_info = ServiceRegistry.get_db_repository(repo_type)
    module_path, class_name = repo_info
    repo_module = importlib.import_module(module_path)
    repo_class = getattr(repo_module, class_name)
    
    # Instantiate with connection and query executor
    repositories[f"{repo_type}_repository"] = repo_class(conn, self.query_executor)

# Create API repositories
for repo_type in service_config.api_repositories:
    repo_info = ServiceRegistry.get_api_repository(repo_type)
    module_path, class_name = repo_info
    repo_module = importlib.import_module(module_path)
    repo_class = getattr(repo_module, class_name)
    
    # API repositories don't need connection
    repositories[f"{repo_type}_repository"] = repo_class(environment="sandbox")
```

**Key detail**: Repository parameter names are derived from repo types:
- Repo type `"cards"` → parameter name `"cards_repository"`
- Repo type `"scryfall"` → parameter name `"scryfall_repository"`

This means service function signatures must match exactly:

```python
# ✓ CORRECT: Parameter names match injected repositories
@ServiceRegistry.register("cards.search", db_repositories=["cards", "ops"])
async def search_service(
    cards_repository: CardRepository,  # ← matches "cards"
    ops_repository: OpsRepository,     # ← matches "ops"
    query: str,
):
    # ...

# ✗ WRONG: Parameter names don't match
@ServiceRegistry.register("cards.search", db_repositories=["cards", "ops"])
async def search_service(
    card_repo: CardRepository,  # ← doesn't match "cards_repository"!
    query: str,
):
    # ...
```

### Step 4: Service Execution

Repositories and caller-provided parameters are merged:

```python
# Merge repositories with caller kwargs
all_kwargs = {**repositories, **kwargs}

# Call service function
result = await service_method(**all_kwargs)
```

### Step 5: Return Value

Services return plain Python objects (dicts, lists, custom dataclasses). The router layer wraps the return value in an HTTP response.

## Decorators & Metadata

The `@ServiceRegistry.register()` decorator accepts several parameters to control execution behavior:

### `db_repositories`

List of database repositories to inject.

```python
@ServiceRegistry.register(
    "cards.search",
    db_repositories=["cards", "pricing"],  # Inject CardRepository and PricingRepository
)
async def search_service(
    cards_repository: CardRepository,
    pricing_repository: PricingRepository,
    query: str,
):
    # ...
```

### `api_repositories`

List of external API repositories to inject (e.g., Scryfall, MTGJson).

```python
@ServiceRegistry.register(
    "cards.fetch_from_scryfall",
    api_repositories=["scryfall"],  # Inject ScryfallRepository
)
async def fetch_from_scryfall(
    scryfall_repository: ScryfallRepository,
    card_name: str,
):
    # ...
```

### `runs_in_transaction`

If `True`, the service runs inside a database transaction (BEGIN/COMMIT/ROLLBACK).

```python
@ServiceRegistry.register(
    "cards.create",
    db_repositories=["cards"],
    runs_in_transaction=True,  # Wrap in transaction
)
async def create_card(cards_repository, name: str, price: float):
    # All queries here run in a transaction
    # Automatic ROLLBACK if any exception occurs
    # ...
```

If `False`, the service gets a raw connection without transaction management (for stored procedures that manage their own transactions):

```python
@ServiceRegistry.register(
    "pricing.load_staging_prices_batched",
    db_repositories=["pricing"],
    runs_in_transaction=False,  # Stored proc manages its own transaction
)
async def load_staging_prices(pricing_repository, ...):
    # ...
```

### `command_timeout`

Maximum time (in seconds) that any single query in the service is allowed to run. Applied on two axes:

1. **Client-side** (asyncpg): The connection's `command_timeout` is set.
2. **Server-side** (PostgreSQL): `SET statement_timeout` is executed.

```python
@ServiceRegistry.register(
    "ops.integrity.scryfall_integrity",
    db_repositories=["ops"],
    command_timeout=60.0,  # 60-second timeout per query
)
async def scryfall_integrity_checks(ops_repository):
    # Any single query taking > 60s is killed
    # ...
```

**Timeout application**:

```python
if service_config.command_timeout is not None:
    # Client-side: Mutate the underlying connection config
    original_config = underlying._config
    underlying._config = original_config._replace(
        command_timeout=service_config.command_timeout
    )
    
    # Server-side: Set Postgres session/local timeout
    scope = "LOCAL" if service_config.runs_in_transaction else "SESSION"
    await conn.execute(
        f"SET {scope} statement_timeout = {int(service_config.command_timeout * 1000)}"
    )
```

### `storage_services`

List of storage backends (local filesystem, S3, etc.) to inject as `StorageService` instances.

```python
@ServiceRegistry.register(
    "mtgstock.download",
    storage_services=["mtgstock_raw", "mtgstock_processed"],
)
async def download_mtgstock(
    mtgstock_raw_storage_service: StorageService,
    mtgstock_processed_storage_service: StorageService,
):
    # Download to mtgstock_raw
    # Process and save to mtgstock_processed
    # ...
```

## Service Lifecycle

Services have a clear lifecycle managed by `ServiceManager`:

### 1. Discovery (Startup)

At app startup, `ServiceManager.initialize()` calls `_discover_services()`:

```python
def _discover_services(self):
    """Import all service modules to register them"""
    from automana.core.settings import get_settings
    from automana.core.data_loader import load_services
    
    settings = get_settings()
    module_namespace = getattr(settings, "modules_namespace")
    modules = SERVICE_MODULES.get(module_namespace, [])
    
    logger.info("loading_service_modules", extra={
        "namespace": module_namespace,
        "modules_count": len(modules),
    })
    
    load_services(modules)  # Import all service modules
```

All service modules in `SERVICE_MODULES` are imported. When a module is imported, the `@ServiceRegistry.register()` decorators execute, registering services in the global `ServiceRegistry`.

### 2. Registration

When a service module is imported, the decorator executes:

```python
# In automana/core/services/cards/search.py

@ServiceRegistry.register(
    "cards.search",
    db_repositories=["cards"],
)
async def search_service(cards_repository, query: str):
    # This function is registered in ServiceRegistry upon import
    # ...
```

The decorator stores metadata in `ServiceRegistry.services` dict:

```python
ServiceRegistry.services["cards.search"] = ServiceConfig(
    module="automana.core.services.cards.search",
    function="search_service",
    db_repositories=["cards"],
    api_repositories=[],
    runs_in_transaction=True,
    command_timeout=30.0,
    storage_services=[],
)
```

### 3. Lookup (Request Time)

When a router calls `service_manager.execute_service("cards.search", ...)`:

```python
service_config = ServiceRegistry.get("cards.search")
# Returns: ServiceConfig with all metadata
```

### 4. Creation (Per Request)

For each request, `ServiceManager` creates a fresh set of repositories:

```python
async def _execute_service(self, service_path: str, **kwargs):
    # Get connection from pool
    async with self._get_connection() as conn:
        # Create new repositories for this request
        repositories = {}
        for repo_type in service_config.db_repositories:
            repositories[f"{repo_type}_repository"] = CardRepository(conn, self.query_executor)
        
        # Execute service with repositories
        result = await service_method(**repositories, **kwargs)
        
        return result
```

### 5. Cleanup (Request End)

After service execution:
- Connection is returned to the pool (reused for next request)
- Repositories are garbage collected
- Transaction is committed or rolled back

## Common Service Keys and Their Responsibilities

Here's a summary of commonly-used service keys across the codebase:

### Authentication & User Management
| Key | Purpose | Repositories |
|-----|---------|--------------|
| `auth.login` | Authenticate user with email/password | user |
| `auth.register` | Create new user account | user |
| `auth.logout` | Invalidate session | user |
| `user_management.get_profile` | Retrieve user profile | user |
| `user_management.update_profile` | Update user details | user |

### Card Catalog
| Key | Purpose | Repositories |
|-----|---------|--------------|
| `cards.search` | Search cards by name/set/price | cards, pricing |
| `cards.get_by_id` | Fetch single card | cards |
| `cards.create` | Create new card record | cards |
| `cards.update_price` | Update card market price | cards, pricing |
| `cards.import_from_csv` | Bulk import cards | cards |

### Operations & Monitoring
| Key | Purpose | Repositories |
|-----|---------|--------------|
| `ops.integrity.scryfall_integrity` | Run Scryfall data sanity checks | ops |
| `ops.integrity.pricing_integrity` | Run pricing data sanity checks | ops |
| `ops.health.alert_service` | Check health and send alerts | ops |
| `ops.pipeline_status` | Get status of background jobs | ops |

### Integrations
| Key | Purpose | Repositories |
|-----|---------|--------------|
| `scryfall.sync_card_catalog` | Fetch latest cards from Scryfall API | cards, scryfall |
| `mtgjson.sync_card_data` | Fetch card metadata from MTGJson | cards, mtgjson |
| `mtgstock.download_prices` | Download pricing data from MTGStock | pricing, mtgstock |
| `ebay.search_listings` | Search eBay for card prices | ebay |

## Code Example: How to Get a Service from ServiceManager

### From a Router

```python
from automana.api.dependancies.dependencies import ServiceManagerDep

@router.get("/api/cards/{card_id}")
async def get_card(
    card_id: int,
    service_manager: ServiceManagerDep,  # Injected by FastAPI
) -> ApiResponse[CardResponse]:
    """Fetch a single card."""
    
    result = await service_manager.execute_service(
        "cards.get_by_id",
        card_id=card_id,
    )
    
    return ApiResponse(data=CardResponse(**result))
```

### From a Celery Task

```python
from celery import shared_task
from automana.core.service_manager import ServiceManager

@shared_task(bind=True)
def sync_scryfall_prices(self):
    """Background job to sync prices."""
    
    # ServiceManager is the singleton
    service_manager = ServiceManager()
    
    # Call execute_service (note: no await in sync context)
    # Use sync wrapper or run_async_in_sync
    result = run_async_in_sync(
        service_manager.execute_service(
            "cards.sync_prices",
        )
    )
    
    return result
```

## Code Example: How to Create a New Service

### Step 1: Create the Service Module

Create a new file in the appropriate service directory, e.g., `src/automana/core/services/cards/search.py`:

```python
"""Card search service."""

import logging
from automana.core.repositories.cards.card_repository import CardRepository
from automana.core.repositories.pricing.price_repository import PriceRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "cards.search",
    db_repositories=["cards", "pricing"],
    runs_in_transaction=True,
    command_timeout=30.0,
)
async def search_service(
    cards_repository: CardRepository,
    pricing_repository: PriceRepository,
    query: str,
    min_price: float | None = None,
    max_price: float | None = None,
) -> dict:
    """
    Search for cards matching query and price filters.
    
    Args:
        query: Card name or keyword to search for
        min_price: Minimum price filter (optional)
        max_price: Maximum price filter (optional)
    
    Returns:
        Dict with keys: total_count, items (list of matching cards)
    """
    
    logger.info(
        "card_search_started",
        extra={
            "query": query,
            "min_price": min_price,
            "max_price": max_price,
        },
    )
    
    # Call repository to get results
    results = await cards_repository.search(
        name=query,
        min_price=min_price,
        max_price=max_price,
    )
    
    # Get pricing info for results
    card_ids = [r["id"] for r in results]
    prices = await pricing_repository.get_latest_prices(card_ids)
    
    # Combine results with prices
    for result in results:
        result["price"] = prices.get(result["id"], 0.0)
    
    logger.info(
        "card_search_completed",
        extra={"query": query, "result_count": len(results)},
    )
    
    return {
        "total_count": len(results),
        "items": results,
    }
```

### Step 2: Ensure Service Module Is Discovered

The service module must be imported during startup. Check `src/automana/core/service_modules.py`:

```python
SERVICE_MODULES = {
    "full": [
        "automana.core.services.cards.search",  # ← Add your module here
        "automana.core.services.cards.create",
        "automana.core.services.auth.login",
        # ... other modules
    ],
}
```

### Step 3: Register Required Repositories (if new types)

If your service uses a new repository type (e.g., `"my_new_repo"`), register it in `src/automana/core/service_registry.py`:

```python
class ServiceRegistry:
    _db_repositories = {
        "cards": ("automana.core.repositories.cards.card_repository", "CardRepository"),
        "pricing": ("automana.core.repositories.pricing.price_repository", "PriceRepository"),
        "my_new_repo": ("automana.core.repositories.my_new.my_new_repository", "MyNewRepository"),  # ← Add this
    }
```

### Step 4: Create a Router to Call the Service

Create a router endpoint that calls your service:

```python
# In src/automana/api/routers/cards.py

from fastapi import APIRouter, Query
from automana.api.dependancies.dependencies import ServiceManagerDep
from automana.api.schemas.responses import ApiResponse

router = APIRouter(prefix="/api/cards", tags=["Cards"])


@router.get("/search", response_model=ApiResponse[dict])
async def search_cards(
    query: str = Query(..., min_length=1),
    min_price: float = Query(None),
    max_price: float = Query(None),
    service_manager: ServiceManagerDep,
) -> ApiResponse[dict]:
    """Search for cards by name and price."""
    
    result = await service_manager.execute_service(
        "cards.search",
        query=query,
        min_price=min_price,
        max_price=max_price,
    )
    
    return ApiResponse(data=result)
```

### Step 5: Test the Service

```python
# tests/unit/core/services/cards/test_search.py

import pytest
from unittest.mock import AsyncMock, patch

from automana.core.services.cards.search import search_service


@pytest.mark.asyncio
async def test_search_service_success():
    """Test service with mocked repositories."""
    
    # Arrange: Mock repositories
    mock_cards_repo = AsyncMock()
    mock_cards_repo.search = AsyncMock(return_value=[
        {"id": 1, "name": "Black Lotus", "set_code": "LTD"},
        {"id": 2, "name": "Lotus Bloom", "set_code": "TSP"},
    ])
    
    mock_pricing_repo = AsyncMock()
    mock_pricing_repo.get_latest_prices = AsyncMock(return_value={
        1: 500.0,
        2: 25.0,
    })
    
    # Act: Call service
    result = await search_service(
        cards_repository=mock_cards_repo,
        pricing_repository=mock_pricing_repo,
        query="lotus",
    )
    
    # Assert: Check result structure
    assert result["total_count"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["price"] == 500.0
```

## Performance Considerations

### Connection Pool Overhead

Each service execution acquires a connection from the pool. The pool is initialized with `min_size` and `max_size`:

```python
async_db_pool = asyncpg.create_pool(
    dsn=settings.database_url,
    min_size=10,
    max_size=20,
)
```

- **Warm start**: If connections are available, acquisition is O(1) and instant.
- **Cold start**: If all connections are busy, a new one is created (up to `max_size`).
- **Timeout**: If `max_size` is reached, the request waits for a connection to be released.

**Optimization**: Monitor pool exhaustion with logging:

```python
logger.info(
    "service_pool_status",
    extra={
        "size": async_db_pool.get_size(),
        "idle": async_db_pool.get_idle_size(),
    },
)
```

### Repository Instantiation

Creating repositories is cheap (O(1)):

```python
repo = CardRepository(conn, executor)  # ← Just wraps the connection
```

No significant overhead.

### Service Lookup

Looking up a service in `ServiceRegistry` is O(1) dict lookup:

```python
service_config = ServiceRegistry.get("cards.search")  # O(1)
```

### Caching Opportunities

Services can cache results in Redis to avoid repeated database queries:

```python
@ServiceRegistry.register("cards.get_by_id", db_repositories=["cards"])
async def get_card_by_id(
    cards_repository,
    card_id: int,
    redis_client: Redis,
) -> dict:
    """Fetch card with caching."""
    
    cache_key = f"card:{card_id}"
    
    # Try cache first
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Fetch from DB
    card = await cards_repository.get_by_id(card_id)
    
    # Cache for 1 hour
    await redis_client.setex(cache_key, 3600, json.dumps(card))
    
    return card
```

## Testing Services in Isolation

Services are designed to be tested in isolation by mocking repositories:

### Unit Test (Mocked Repositories)

```python
@pytest.mark.asyncio
async def test_search_service_filters_by_price(mocker):
    """Test service business logic without database."""
    
    # Arrange
    mock_cards_repo = AsyncMock()
    mock_cards_repo.search = AsyncMock(return_value=[
        {"id": 1, "name": "Card A", "price": 0.50},
        {"id": 2, "name": "Card B", "price": 50.0},
    ])
    
    # Act: Search with min price filter
    result = await search_service(
        cards_repository=mock_cards_repo,
        query="",
        min_price=5.0,  # Filter out cheap card
    )
    
    # Assert: Only expensive card is returned
    assert len(result["items"]) == 1
    assert result["items"][0]["price"] == 50.0
```

### Integration Test (Real ServiceManager)

```python
@pytest.mark.asyncio
async def test_search_service_integration(async_service_manager):
    """Test service with real ServiceManager and database."""
    
    # The service_manager fixture initializes a real database and ServiceManager
    result = await async_service_manager.execute_service(
        "cards.search",
        query="Black Lotus",
    )
    
    assert result["total_count"] > 0
```

## See Also

- [`docs/LAYERED_ARCHITECTURE.md`](LAYERED_ARCHITECTURE.md) — Layer 2: Service responsibilities
- [`docs/DESIGN_PATTERNS.md`](../../DESIGN_PATTERNS.md) — Service patterns and best practices
- [`src/automana/core/service_registry.py`](../../src/automana/core/service_registry.py) — ServiceRegistry implementation
- [`src/automana/core/service_manager.py`](../../src/automana/core/service_manager.py) — ServiceManager implementation
