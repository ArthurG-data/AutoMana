# Design Patterns Lexicon

This document catalogues every distinct design pattern found in the AutoMana codebase. Each entry gives the canonical pattern name, a description of how it is applied, the exact file(s) and line ranges where it appears, and a concise explanation of why that pattern was chosen.

---

## Table of Contents

1. [Singleton](#1-singleton)
2. [Service Registry (Registry Pattern)](#2-service-registry-registry-pattern)
3. [Service Layer](#3-service-layer)
4. [Repository](#4-repository)
5. [Dependency Injection](#5-dependency-injection)
6. [Decorator (Registration Decorator)](#6-decorator-registration-decorator)
7. [Chain of Responsibility (Celery Chain)](#7-chain-of-responsibility-celery-chain)
8. [Context Object](#8-context-object)
9. [Strategy](#9-strategy)
10. [Template Method](#10-template-method)
11. [Facade](#11-facade)
12. [Factory (Dynamic Instantiation)](#12-factory-dynamic-instantiation)
13. [Abstract Base Class (Interface Segregation)](#13-abstract-base-class-interface-segregation)
14. [Observer (Signal-based Lifecycle)](#14-observer-signal-based-lifecycle)
15. [Proxy (Error-Mapping Proxy)](#15-proxy-error-mapping-proxy)
16. [Data Transfer Object (DTO)](#16-data-transfer-object-dto)
17. [Unit of Work (Transaction Wrapper)](#17-unit-of-work-transaction-wrapper)
18. [Idempotent Guard](#18-idempotent-guard)
19. [Retry with Exponential Backoff](#19-retry-with-exponential-backoff)
20. [Layered Exception Hierarchy](#20-layered-exception-hierarchy)
21. [Thread-Confined Event Loop](#21-thread-confined-event-loop)
22. [Module Namespace Selector](#22-module-namespace-selector)

---

## 1. Singleton

**Where:** [`src/automana/core/service_manager.py`](../src/automana/core/service_manager.py), lines 14--27

**Implementation:** `ServiceManager` overrides `__new__` to ensure only one instance exists across the entire process. The `_initialized` flag prevents `__init__` from running more than once. A class-level `_instance` attribute holds the singleton.

```python
class ServiceManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ServiceManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
```

**Why:** Both the FastAPI lifespan and the Celery worker bootstrap need to share exactly one `ServiceManager` holding the connection pool and query executor. The singleton guarantees a single point of dispatch for all service calls regardless of entry point (HTTP, Celery task, CLI, TUI). It also prevents accidental re-initialization of the service registry.

---

## 2. Service Registry (Registry Pattern)

**Where:** [`src/automana/core/service_registry.py`](../src/automana/core/service_registry.py), entire file (lines 1--215)

**Implementation:** `ServiceRegistry` is a class with class-level dictionaries that act as in-memory registries:

| Registry | Maps | Purpose |
|---|---|---|
| `_services` | dotted path -> `ServiceConfig` | Service functions and their dependency declarations |
| `_repository_registry` | name -> (module, class) | DB repository classes |
| `_api_repository_registry` | name -> (module, class) | External API repository classes |
| `_storage_backend_registry` | name -> (module, class) | Storage backend implementations |
| `_storage_registry` | logical name -> config dict | Named storage instances |

Services register via the `@register` decorator. Repositories and storages are registered imperatively at module load time (lines 128--215).

**Why:** Decouples service discovery from service implementation. A router or Celery task only needs to know a string key (`"card_catalog.card.search"`), not an import path. This makes it possible to swap implementations, load different module sets per runtime (HTTP vs. Celery), and list all available services programmatically (used by `automana-run` and the TUI).

---

## 3. Service Layer

**Where:** [`src/automana/core/services/`](../src/automana/core/services/) -- all files in this directory tree

**Representative file:** [`src/automana/core/services/card_catalog/card_service.py`](../src/automana/core/services/card_catalog/card_service.py)

**Implementation:** Each service is a plain async function decorated with `@ServiceRegistry.register(...)`. Services declare their dependencies (DB repositories, API repositories, storage services) in the decorator. The `ServiceManager` injects these dependencies at call time. Services contain business logic and coordinate between repositories.

**Why:** Keeps business logic out of routers and Celery tasks. The service layer is the only place where business rules are enforced, which means the same logic is exercised whether a request comes from HTTP, a background job, the CLI, or the TUI. This is a core architectural invariant: **routers must never access the database directly**.

---

## 4. Repository

**Where:**
- Abstract base: [`src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`](../src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py) (lines 1--92)
- Abstract API base: [`src/automana/core/repositories/abstract_repositories/AbstractAPIRepository.py`](../src/automana/core/repositories/abstract_repositories/AbstractAPIRepository.py) (lines 1--187)
- Concrete DB repos: [`src/automana/core/repositories/`](../src/automana/core/repositories/) (card_catalog, ops, app_integration, analytics subdirectories)
- Concrete API repos: e.g., `src/automana/core/repositories/app_integration/scryfall/ApiScryfall_repository.py`

**Implementation:** `AbstractRepository` is a generic ABC that enforces a standard CRUD interface (`add`, `get`, `update`, `delete`, `list`). Concrete repositories inherit from it and receive a DB connection + `QueryExecutor` at construction time. `BaseApiClient` serves the same role for external HTTP APIs, providing `send()`, response parsing, and error mapping.

**Why:** Encapsulates all data access (both database and external API) behind a stable interface. This enforces the layered architecture: services never write raw SQL or make HTTP calls directly -- they delegate to repositories. It also makes testing easier (repositories can be swapped) and keeps SQL/HTTP concerns out of business logic.

---

## 5. Dependency Injection

**Where:**
- FastAPI DI: [`src/automana/api/dependancies/service_deps.py`](../src/automana/api/dependancies/service_deps.py) (lines 1--44)
- Auth DI: [`src/automana/api/dependancies/auth/users.py`](../src/automana/api/dependancies/auth/users.py) (lines 1--50)
- Query params DI: [`src/automana/api/dependancies/query_deps.py`](../src/automana/api/dependancies/query_deps.py) (lines 1--121)
- ServiceManager-level DI: [`src/automana/core/service_manager.py`](../src/automana/core/service_manager.py), `_execute_service` method (lines 177--244)

**Implementation:** Two levels of DI operate in AutoMana:

1. **FastAPI `Depends()`**: Router functions declare typed dependencies (`ServiceManagerDep`, `CurrentUserDep`, `PaginationParams`, `SortParams`, `ipDep`, etc.) using `Annotated[Type, Depends(factory)]`. FastAPI resolves these at request time.

2. **ServiceManager auto-injection**: When `_execute_service` is called, it reads the service's declared `db_repositories`, `api_repositories`, and `storage_services` from the registry, dynamically imports and instantiates each one, and passes them as keyword arguments to the service function.

**Why:** Eliminates manual wiring and circular imports. Routers do not import repositories or create connections. Services do not import or instantiate their own dependencies. This makes the dependency graph explicit (declared in the decorator) and testable.

---

## 6. Decorator (Registration Decorator)

**Where:** [`src/automana/core/service_registry.py`](../src/automana/core/service_registry.py), `register` classmethod (lines 33--62)

**Implementation:** `@ServiceRegistry.register(path, db_repositories=[...], ...)` wraps a function without modifying its behavior. The decorator's sole purpose is the side effect of registering the function's metadata (module, function name, dependency declarations) in the `_services` dictionary.

```python
@ServiceRegistry.register(
    "card_catalog.card.search",
    db_repositories=["card"]
)
async def search_cards(card_repository, **kwargs):
    ...
```

**Why:** Keeps registration close to the implementation. When reading a service file, you immediately see its registry path and dependencies. There is no separate configuration file to keep in sync. The function itself is returned unmodified, so there is no runtime overhead.

---

## 7. Chain of Responsibility (Celery Chain)

**Where:** [`src/automana/worker/tasks/pipelines.py`](../src/automana/worker/tasks/pipelines.py), lines 1--72

**Implementation:** Each pipeline (e.g., `daily_scryfall_data_pipeline`) is defined as a Celery `chain()` of `run_service.s(service_path, **kwargs)` calls. Each step in the chain receives the previous step's result as the `prev` argument. The `run_service` task (in `worker/main.py`, lines 32--84) merges the result dict into a running `context` dict and filters it to only the parameter names accepted by the next service function (using `inspect.signature`).

```python
wf = chain(
    run_service.s("staging.scryfall.start_pipeline", ...),
    run_service.s("staging.scryfall.get_bulk_data_uri"),
    run_service.s("staging.scryfall.download_bulk_manifests"),
    ...
)
```

**Why:** Pipeline steps are independent service functions that can be tested and run individually (via `automana-run`). The chain provides ordered execution with automatic context propagation. If a step fails, the chain halts and the error is logged with full context. The signature-based filtering ensures each step only receives the parameters it expects, preventing accidental coupling.

**Non-negotiable rule:** Pipeline tasks in `pipelines.py` must not use `autoretry_for`. Retry logic is handled at the `run_service` level.

---

## 8. Context Object

**Where:** [`src/automana/worker/main.py`](../src/automana/worker/main.py), `run_service` function (lines 38--84)

**Implementation:** The `context` dict accumulates key-value pairs across chain steps. Each step's result (if a dict) is merged into `context` with `context.update(result)`. Before calling the next service, `context` is filtered against the function's parameter names. This flowing dict is the "context object" of the pipeline.

**Why:** Pipeline steps need to pass data forward (e.g., `ingestion_run_id` from step 1 is needed by all subsequent steps). Rather than requiring each step to explicitly declare and forward every upstream value, the context object carries the full accumulated state. The signature-based filtering keeps each step's interface clean while the context handles the plumbing.

---

## 9. Strategy

**Where:**
- Storage backends: [`src/automana/core/storage.py`](../src/automana/core/storage.py) -- `StorageBackend` ABC (lines 13--50) and `LocalStorageBackend` (lines 51--193)
- Query executors: [`src/automana/core/QueryExecutor.py`](../src/automana/core/QueryExecutor.py) -- `QueryExecutor` ABC (lines 13--44), `SyncQueryExecutor` (lines 46--74), `AsyncQueryExecutor` (lines 77--124)
- Exception handlers: [`src/automana/api/request_handling/ErrorHandler.py`](../src/automana/api/request_handling/ErrorHandler.py) -- `ExceptionHandler` protocol (lines 10--30), `Psycopg2ExceptionHandler` (lines 32--52), `AsyncpgExceptionHandler` (lines 54--70)

**Implementation:** In each case, an abstract interface defines the contract (e.g., `save`, `load`, `delete` for storage; `execute_query`, `execute_command` for query execution; `handle`, `handle_async` for error handling). Concrete implementations provide the behavior. The consumer (`StorageService`, `AbstractRepository`, `AsyncQueryExecutor`) receives the strategy at construction time.

**Why:** Makes the system extensible without modifying existing code. Adding S3 storage means writing a new `S3StorageBackend` class without changing `StorageService`. The same separation allows async and sync query execution to coexist, and different DB drivers (asyncpg vs. psycopg2) to use appropriate error handlers.

---

## 10. Template Method

**Where:** [`src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`](../src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py), lines 1--92

**Implementation:** `AbstractRepository` defines concrete methods (`execute_query`, `execute_command`, `execute_query_sync`, `execute_command_sync`) that handle the mechanics of query execution (delegating to the executor or falling back to direct connection use). Subclasses implement the abstract methods (`add`, `get`, `update`, `delete`, `list`) to define entity-specific queries.

Similarly, `BaseApiClient` in [`AbstractAPIRepository.py`](../src/automana/core/repositories/abstract_repositories/AbstractAPIRepository.py) provides the concrete `send()` method (lines 145--186) with error handling and response parsing, while subclasses override `_get_base_url()`, `default_headers()`, and `name` to specialize for each external API.

**Why:** Common infrastructure (connection handling, error mapping, response parsing) is written once in the base class. Subclasses only need to provide the domain-specific parts. This eliminates boilerplate and ensures consistent error handling across all repositories.

---

## 11. Facade

**Where:**
- [`src/automana/core/storage.py`](../src/automana/core/storage.py), `StorageService` class (lines 195--261)
- [`src/automana/core/service_manager.py`](../src/automana/core/service_manager.py), `ServiceManager` class

**Implementation:** `StorageService` wraps a `StorageBackend` and exposes higher-level operations (`save_json`, `load_json`, `save_binary`, `save_with_timestamp`, `list_directory`, etc.) that combine backend primitives with naming conventions and format handling. Services interact with `StorageService` without knowing which backend is in use.

`ServiceManager` similarly facades the entire service execution pipeline: registry lookup, module import, repository instantiation, transaction management, and service invocation -- all behind a single `execute_service(path, **kwargs)` call.

**Why:** Simplifies the interface for callers. A service function calls `storage_service.save_json(filename, data)` rather than dealing with path resolution, directory creation, JSON serialization, and backend selection. The facade hides complexity and provides a stable API even as internals evolve.

---

## 12. Factory (Dynamic Instantiation)

**Where:** [`src/automana/core/service_manager.py`](../src/automana/core/service_manager.py), `_execute_service` method (lines 177--244) and `get_storage_service` method (lines 128--159)

**Implementation:** When `_execute_service` runs, it dynamically imports repository modules and instantiates repository classes based on the registered module path and class name. It passes the current DB connection and query executor to DB repositories, and the environment to API repositories. `get_storage_service` similarly resolves a named storage to a backend class and instantiates it with the appropriate config.

```python
module_path, class_name = repo_info
repo_module = importlib.import_module(module_path)
repo_class = getattr(repo_module, class_name)
repositories[f"{repo_type}_repository"] = repo_class(conn, self.query_executor)
```

**Why:** Repositories are created per-request within a transaction scope, ensuring each service call gets its own connection-scoped repository instances. Dynamic import avoids circular dependencies and allows the registry to be populated at module load time without eagerly importing every repository module.

---

## 13. Abstract Base Class (Interface Segregation)

**Where:**
- [`src/automana/core/QueryExecutor.py`](../src/automana/core/QueryExecutor.py), `QueryExecutor` ABC (lines 13--44)
- [`src/automana/core/storage.py`](../src/automana/core/storage.py), `StorageBackend` ABC (lines 13--50)
- [`src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py`](../src/automana/core/repositories/abstract_repositories/AbstractDBRepository.py), `AbstractRepository` ABC (lines 9--92)
- [`src/automana/api/request_handling/ErrorHandler.py`](../src/automana/api/request_handling/ErrorHandler.py), `ExceptionHandler` protocol (lines 10--30)

**Implementation:** Each ABC/Protocol defines the minimum set of methods that implementations must provide. `QueryExecutor` requires `execute_command` and `execute_query`. `StorageBackend` requires `open_stream`, `save`, `load`, `exists`, `delete`, `list_files`, `get_file_size`. `ExceptionHandler` uses `typing.Protocol` with `runtime_checkable` for structural subtyping.

**Why:** Enforces contracts at the type level. If a new storage backend or query executor does not implement the required methods, the error is caught early. The protocol-based `ExceptionHandler` allows duck typing without requiring inheritance.

---

## 14. Observer (Signal-based Lifecycle)

**Where:** [`src/automana/worker/main.py`](../src/automana/worker/main.py), lines 18--25

**Implementation:** Celery signals `worker_process_init` and `worker_process_shutdown` are used to hook into the worker lifecycle:

```python
@worker_process_init.connect
def _init(**_):
    configure_logging()
    init_backend_runtime()

@worker_process_shutdown.connect
def _shutdown(**_):
    shutdown_backend_runtime()
```

**Why:** Celery worker processes need to initialize their own async event loop, DB pool, and `ServiceManager` (since these cannot be inherited from the parent process after fork). The observer/signal pattern lets the initialization code respond to Celery's lifecycle events without modifying Celery's internals.

---

## 15. Proxy (Error-Mapping Proxy)

**Where:** [`src/automana/api/request_handling/ErrorHandler.py`](../src/automana/api/request_handling/ErrorHandler.py), `AsyncpgExceptionHandler` and `Psycopg2ExceptionHandler` (lines 32--70)

**Also:** [`src/automana/core/repositories/abstract_repositories/AbstractAPIRepository.py`](../src/automana/core/repositories/abstract_repositories/AbstractAPIRepository.py), `map_http_error` method (lines 91--143)

**Implementation:** These classes intercept low-level exceptions (asyncpg violations, psycopg2 errors, httpx status errors) and translate them into appropriate application-level exceptions (HTTPException with correct status codes, or typed `RepositoryError` subclasses). The `AsyncQueryExecutor` delegates to its error handler after catching database exceptions.

**Why:** Prevents low-level driver details from leaking into the service layer or HTTP responses. A `UniqueViolationError` from asyncpg becomes a clean HTTP 409 with "Conflict: Duplicate entry." -- the router does not need to know which database driver is in use. The external API proxy in `BaseApiClient.map_http_error` similarly normalizes third-party HTTP errors into a typed exception hierarchy.

---

## 16. Data Transfer Object (DTO)

**Where:**
- [`src/automana/api/schemas/StandardisedQueryResponse.py`](../src/automana/api/schemas/StandardisedQueryResponse.py), `ApiResponse`, `PaginatedResponse`, `ErrorResponse` (lines 1--31)
- [`src/automana/api/dependancies/query_deps.py`](../src/automana/api/dependancies/query_deps.py), `PaginationParams`, `SortParams`, `DateRangeParams` (lines 8--26)
- [`src/automana/core/models/`](../src/automana/core/models/) -- Pydantic models for cards, sets, pipelines, etc.
- [`src/automana/core/services/card_catalog/card_service.py`](../src/automana/core/services/card_catalog/card_service.py), `CardSearchResult`, `ProcessingStats`, `ProcessingConfig` dataclasses (lines 19--60)

**Implementation:** Pydantic `BaseModel` subclasses and Python `@dataclass` classes carry data between layers without containing business logic. `ApiResponse[T]` is generic, wrapping any data type in a consistent envelope. Processing stats are dataclasses with computed properties.

**Why:** Standardizes the shape of data crossing layer boundaries. The generic `ApiResponse[T]` ensures every endpoint returns a consistent envelope. Processing dataclasses (`ProcessingStats`, `ProcessingConfig`) provide type-safe configuration and statistics tracking without coupling to any specific service implementation.

---

## 17. Unit of Work (Transaction Wrapper)

**Where:** [`src/automana/core/service_manager.py`](../src/automana/core/service_manager.py), `transaction` async context manager (lines 69--86)

**Implementation:** The `transaction()` method acquires a connection from the pool, starts a database transaction, yields the connection, and either commits on success or rolls back on exception. Every service execution goes through this context manager (line 202: `async with self.transaction() as conn:`).

```python
@asynccontextmanager
async def transaction(self):
    connection = await self.connection_pool.acquire()
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
        await transaction.commit()
    except Exception:
        await transaction.rollback()
        raise
    finally:
        await self.connection_pool.release(connection)
```

**Why:** Guarantees that all repository operations within a single service call are atomic. If any operation fails, the entire service call's database changes are rolled back. This is especially important for pipeline steps that write to multiple tables (e.g., creating a run record and updating steps in the same call).

---

## 18. Idempotent Guard

**Where:**
- Logging: [`src/automana/core/logging_config.py`](../src/automana/core/logging_config.py), `configure_logging` function (lines 52--70) -- uses `_automana_configured` flag
- Pipeline runs: [`src/automana/core/repositories/ops/ops_repository.py`](../src/automana/core/repositories/ops/ops_repository.py), `start_run` method (lines 43--140) -- uses `ON CONFLICT` with CTE guard `already_started_successfully`

**Implementation:** `configure_logging()` checks a custom flag on the root logger (`_automana_configured`) and returns immediately if already set. This allows it to be called safely from both module-level code and signal handlers. The `start_run` SQL uses a CTE that checks whether a run with the same `(pipeline_name, source_id, run_key)` has already completed its start step; if so, the INSERT is skipped entirely.

**Why:** Both the FastAPI lifespan and Celery worker signals call `configure_logging()`. Without the guard, duplicate handlers would be attached. Pipeline idempotency is critical because Beat may re-trigger a pipeline on the same calendar day, and manual re-runs must be safe. The SQL-level guard prevents duplicate run records.

---

## 19. Retry with Exponential Backoff

**Where:**
- DB pool creation: [`src/automana/core/database.py`](../src/automana/core/database.py), `init_async_pool` (lines 16--55) and `init_sync_pool_with_retry` (lines 70--101)
- HTTP client: [`src/automana/worker/http_utils.py`](../src/automana/worker/http_utils.py), `get` function (lines 7--17)
- Celery `run_service` task: [`src/automana/worker/main.py`](../src/automana/worker/main.py), lines 32--37 (`autoretry_for`, `retry_backoff=True`)

**Implementation:** `_compute_backoff_seconds` calculates `base_delay * 2^(attempt-1)` capped at `max_delay`. The DB pool init loops up to `DB_CONNECT_MAX_ATTEMPTS` times with increasing delays. The HTTP utility uses `min(2^attempt, 10)` seconds for 429/5xx responses. The `run_service` Celery task uses Celery's built-in `retry_backoff`.

**Why:** Infrastructure dependencies (Postgres, Redis, external APIs) are not always immediately available at startup, especially in containerized environments where services start in parallel. Backoff prevents thundering-herd retries and gives dependent services time to become ready.

---

## 20. Layered Exception Hierarchy

**Where:**
- Base: [`src/automana/core/exceptions/base_exception.py`](../src/automana/core/exceptions/base_exception.py), `ServiceError` (line 1)
- Repository base: [`src/automana/core/exceptions/repository_layer_exceptions/base_repository_exception.py`](../src/automana/core/exceptions/repository_layer_exceptions/base_repository_exception.py), `RepositoryError` (lines 1--85)
- API errors: [`src/automana/core/exceptions/repository_layer_exceptions/api_errors.py`](../src/automana/core/exceptions/repository_layer_exceptions/api_errors.py), `ExternalApiError` and subclasses (lines 1--27)

**Implementation:** A three-tier hierarchy:

```
ServiceError (base)
  |
  RepositoryError (adds error_code, status_code, error_data, source_exception, to_dict, from_exception)
    |
    ExternalApiError
      |-- ExternalApiConnectionError
      |-- ExternalApiHttpError
            |-- ExternalApiUnauthorizedError
            |-- ExternalApiForbiddenError
            |-- ExternalApiNotFoundError
            |-- ExternalApiRateLimitError
            |-- ExternalApiMethodNotAllowedError
```

**Why:** Typed exceptions allow catch blocks to be precise. The service layer can catch `ExternalApiRateLimitError` specifically (to implement backoff) without catching `ExternalApiNotFoundError`. The `RepositoryError.to_dict()` method provides a serializable representation for logging and API responses. The `from_exception` class method enables clean exception wrapping.

---

## 21. Thread-Confined Event Loop

**Where:**
- Celery: [`src/automana/worker/ressources.py`](../src/automana/worker/ressources.py), `init_backend_runtime` (lines 18--35)
- Utility: [`src/automana/worker/async_runner.py`](../src/automana/worker/async_runner.py), `AsyncRunner` class (lines 1--22)

**Implementation:** Celery workers are synchronous. `init_backend_runtime` creates a dedicated `asyncio` event loop for the worker process and stores it in `CeleryAppState`. The `run_service` task uses `state.loop.run_until_complete(...)` to bridge sync-to-async. `AsyncRunner` takes this further by running the loop on a dedicated daemon thread, useful for concurrent async calls from a sync context.

**Why:** The service layer and all repositories are async (they use asyncpg, which requires an event loop). Celery tasks are synchronous. The thread-confined loop bridges this gap without blocking the Celery prefork worker model. Each worker process gets its own loop, avoiding cross-process state sharing.

---

## 22. Module Namespace Selector

**Where:** [`src/automana/core/service_modules.py`](../src/automana/core/service_modules.py), `SERVICE_MODULES` dict (lines 1--47)

**Implementation:** A dictionary maps namespace names (`"backend"`, `"celery"`, `"all"`) to lists of service module paths. During `ServiceManager._discover_services()`, the active namespace (from `settings.modules_namespace`) determines which modules are imported. Modules not in the list are never loaded, so their `@ServiceRegistry.register` decorators never fire.

**Why:** The FastAPI backend and Celery worker need different subsets of services. The backend loads user-facing services (auth, browsing, collections) that Celery does not need. Celery loads pipeline and analytics services that the backend does not need. Loading only the relevant modules reduces startup time, memory usage, and the risk of import errors from missing dependencies.

---

## Pipeline Step Tracking (Domain-Specific Pattern)

**Where:** [`src/automana/core/services/ops/pipeline_services.py`](../src/automana/core/services/ops/pipeline_services.py), `track_step` async context manager (lines 9--44)

**Implementation:** An async context manager that wraps a pipeline step. On entry, it marks the step as `running` in the ops repository. On clean exit, it marks it as `success`. On exception, it records the failure and re-raises.

```python
@asynccontextmanager
async def track_step(ops_repository, ingestion_run_id, step_name, ...):
    await ops_repository.update_run(ingestion_run_id, status="running", current_step=step_name)
    try:
        yield
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", ...)
        raise
    else:
        await ops_repository.update_run(ingestion_run_id, status="success", ...)
```

**Why:** Provides structured observability for ETL pipelines. Every step's start time, end time, and status are recorded in `ops.ingestion_run_steps`. When a pipeline fails, operators can query the ops tables to see exactly which step failed and why, without parsing logs. The context manager is a no-op when `ops_repository` is `None`, allowing services to run standalone (via CLI) without ops tracking.

---

## Summary of Pattern Distribution

| Pattern | Primary Location | Also Used In |
|---|---|---|
| Singleton | `service_manager.py` | |
| Registry | `service_registry.py` | |
| Service Layer | `core/services/` | |
| Repository | `core/repositories/` | `api/repositories/` |
| Dependency Injection | `api/dependancies/`, `service_manager.py` | |
| Decorator | `service_registry.py` | |
| Chain of Responsibility | `worker/tasks/pipelines.py` | |
| Context Object | `worker/main.py` (run_service) | |
| Strategy | `storage.py`, `QueryExecutor.py`, `ErrorHandler.py` | |
| Template Method | `AbstractDBRepository.py`, `AbstractAPIRepository.py` | |
| Facade | `storage.py` (StorageService), `service_manager.py` | |
| Factory | `service_manager.py` (_execute_service, get_storage_service) | |
| ABC / Interface | `QueryExecutor.py`, `storage.py`, `AbstractDBRepository.py` | `ErrorHandler.py` |
| Observer | `worker/main.py` (Celery signals) | |
| Proxy | `ErrorHandler.py`, `AbstractAPIRepository.py` | |
| DTO | `StandardisedQueryResponse.py`, `query_deps.py`, `core/models/` | |
| Unit of Work | `service_manager.py` (transaction) | |
| Idempotent Guard | `logging_config.py`, `ops_repository.py` | |
| Retry + Backoff | `database.py`, `http_utils.py`, `worker/main.py` | |
| Exception Hierarchy | `core/exceptions/` | |
| Thread-Confined Loop | `worker/ressources.py`, `async_runner.py` | |
| Namespace Selector | `service_modules.py`, `service_manager.py` | |
| Step Tracking | `pipeline_services.py` | |

---

## Non-Negotiable Rules (Cross-Reference)

These architectural rules are enforced by the patterns above:

| Rule | Enforced By |
|---|---|
| No direct DB access from routers | Service Layer + DI (routers only get `ServiceManagerDep`, never a connection) |
| No `logging.basicConfig()` | Idempotent Guard (`configure_logging()` with `_automana_configured` flag) |
| No reserved `LogRecord` keys in `extra={}` | `_RESERVED` set in `logging_config.py` (line 12) filters collisions in `JsonFormatter` |
| No `autoretry_for` in pipeline tasks | Chain pattern (retry at `run_service` level, not per-pipeline-task) |
| All config via `core/settings.py` | Strategy (`Settings` with Pydantic `BaseSettings`, `@lru_cache`, secret cascade) |
| Schema changes need a migration | Repository pattern (all DDL under `database/SQL/migrations/`, enforced by `db_owner` RBAC) |
