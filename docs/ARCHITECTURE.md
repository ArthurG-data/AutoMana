
# AutoMana Architecture

This document explains how the backend is structured, how requests flow through the system, and where to add new features safely.

If you want the *exact* API surface, use `GET /docs` and `GET /openapi.json`.

For the complete catalogue of design patterns used in this codebase, see [`docs/DESIGN_PATTERNS.md`](DESIGN_PATTERNS.md).

## High-level overview

AutoMana is a FastAPI application backed by PostgreSQL (+ TimescaleDB + pgvector), with background processing via Celery/Redis, and a reverse proxy (nginx) in production.

### Layer Diagram

![Architecture Layers](diagrams/layer_diagramm.jpg)

### Production topology (Docker)

In production, only the reverse proxy should publish ports to the host.

```
Internet
	|
	v
nginx proxy (ports 80/443 published)
	|
	v
FastAPI backend (internal network only)
	|
	+--> Postgres (internal network only)
	+--> Redis (internal network only)
	+--> db-backup (internal network only)
```

Reference compose file: `deploy/docker-compose.prod.yml`.

## Backend runtime

### Entry point and lifespan

The FastAPI app is created in [`src/automana/api/main.py`](../src/automana/api/main.py).

On startup (lifespan):

- Calls `configure_logging()` (idempotent)
- Initializes an async DB pool (asyncpg) and a sync pool (psycopg2), both with retry/backoff
- Creates an `AsyncQueryExecutor` with the `AsyncpgExceptionHandler`
- Initializes the singleton `ServiceManager` which discovers and registers all service modules

On shutdown:

- Closes the `ServiceManager`
- Closes async and sync DB pools

### Request flow (HTTP)

Typical request flow:

1. Client calls an endpoint under `/api/...`
2. Middleware assigns a `request_id` (UUID) and `service_path` to the logging context
3. Router function uses dependency injection to obtain:
	 - `ServiceManagerDep` (the `ServiceManager` singleton)
	 - optionally `CurrentUserDep` (session-cookie auth)
	 - pagination/sort/search dependencies for list endpoints
4. Router calls `service_manager.execute_service("some.service.key", **kwargs)`
5. `ServiceManager` looks up the service in `ServiceRegistry`, imports the module, instantiates required repositories (DB and API) within a transaction, and calls the service function
6. Response is wrapped in `ApiResponse`/`PaginatedResponse`

Key DI wiring lives in [`src/automana/api/dependancies/service_deps.py`](../src/automana/api/dependancies/service_deps.py).

### Request flow (Celery)

Background task flow:

1. Celery Beat triggers a pipeline task (e.g., `daily_scryfall_data_pipeline`)
2. The pipeline builds a `chain()` of `run_service.s(service_path, **kwargs)` calls
3. Each `run_service` task: resolves the service function, filters kwargs to match its signature (via `inspect.signature`), executes via `ServiceManager.execute_service`, and merges the result dict into the chain context for the next step
4. The same service layer, repositories, and transaction management are used as in the HTTP path

## Modules and responsibilities

### API layer (routing)

Routes are organized under [`src/automana/api/routers/`](../src/automana/api/routers/).

- Global API router: [`src/automana/api/__init__.py`](../src/automana/api/__init__.py) (prefix `/api`)
- Major areas:
	- Catalog (cards, sets, collections): `/api/catalog/mtg/...`
	- Users/auth/sessions: `/api/users/...`
	- Integrations (eBay, Shopify, MTGStock): `/api/integrations/...`
	- Logs: `/api/logs/...`

This layer should stay thin: validation, dependency wiring, and calling services. **Routers must never access the database directly.**

### Service layer

The service layer lives under [`src/automana/core/services/`](../src/automana/core/services/) and is orchestrated by [`src/automana/core/service_manager.py`](../src/automana/core/service_manager.py).

- The `ServiceManager` is a singleton that dispatches calls to services registered in the `ServiceRegistry`.
- Services register themselves using the `@ServiceRegistry.register` decorator, declaring their service path, required DB repositories, API repositories, and storage services.
- Routers call `execute_service(...)` with a dotted service key instead of importing the implementation directly.

This gives you a single place to:

- control dependencies (repositories and storage are injected automatically)
- reuse services from HTTP endpoints, Celery tasks, CLI tools, or the TUI
- swap implementations without changing routers

Service modules are grouped into namespaces (`backend`, `celery`, `all`) in [`src/automana/core/service_modules.py`](../src/automana/core/service_modules.py). The active namespace is set by the `MODULES_NAMESPACE` setting.

### Metric registry (`core/metrics/`)

`src/automana/core/metrics/` houses the `MetricRegistry` — a decorator-based registry parallel to `ServiceRegistry`, scoped to sanity-report metrics. Each metric is an async function that queries a small, well-defined slice of the DB and returns a `MetricResult`. Runner services (e.g., `ops.integrity.mtgstock_report`) call `MetricRegistry.select(prefix=..., category=..., names=...)` to pick a subset and wrap the results in the standard integrity-report envelope.

See [`docs/METRICS_REGISTRY.md`](METRICS_REGISTRY.md) for the full API and how to add new metrics.

### Repository/data access layer

Repositories live under [`src/automana/core/repositories/`](../src/automana/core/repositories/) and extend `AbstractRepository` (DB) or `BaseApiClient` (external API).

The backend uses:

- async DB access (asyncpg) for all service calls in the HTTP and Celery paths
- sync DB access (psycopg2) available for special cases

Pool initialization lives in [`src/automana/core/database.py`](../src/automana/core/database.py), with configurable retry/backoff.

### Standard response shapes

Standard response envelopes are defined in [`src/automana/api/schemas/StandardisedQueryResponse.py`](../src/automana/api/schemas/StandardisedQueryResponse.py):

- `ApiResponse` — single-item or list responses
- `PaginatedResponse` — paginated list responses with `PaginationInfo`
- `ErrorResponse` — error responses

### Authentication & authorization

AutoMana uses a split-transport auth model:

- **Session cookie (`session_id`)** — `httponly=True`, `samesite=strict`. Set at login; used by browser/cookie clients. The `CurrentUserDep` dependency reads this cookie and resolves the user via the service layer. The `secure` flag is on in all non-`dev` environments (staging, prod sit behind the nginx TLS terminator).
- **JWT in response body** — `/api/users/auth/token` returns `access_token` in the JSON body only (no `access_token` cookie). Programmatic callers pass it as `Authorization: Bearer <jwt>`. The `check_token_validity` dependency in `auth_service.py` accepts Bearer tokens only.

These two paths are intentionally separate: cookie auth for interactive clients, Bearer for API callers.

Session state is stored in `user_management.v_active_sessions` (schema-qualified view). All session mutations go through stored functions (`user_management.insert_add_token`, `user_management.rotate_refresh_token`, `user_management.inactivate_session`).

Key files:
- [`src/automana/api/dependancies/auth/users.py`](../src/automana/api/dependancies/auth/users.py) — `CurrentUserDep`
- [`src/automana/api/services/auth/auth_service.py`](../src/automana/api/services/auth/auth_service.py) — `check_token_validity`, `login`, `logout`
- [`src/automana/api/repositories/auth/session_repository.py`](../src/automana/api/repositories/auth/session_repository.py) — session DB access

### Background jobs (Celery)

Celery configuration and app wiring:

- [`src/automana/worker/main.py`](../src/automana/worker/main.py) — Celery app creation, `run_service` task, worker lifecycle signals
- [`src/automana/worker/celeryconfig.py`](../src/automana/worker/celeryconfig.py) — broker/result backend URLs, Beat schedule, task imports
- [`src/automana/worker/ressources.py`](../src/automana/worker/ressources.py) — per-worker-process async event loop and `ServiceManager` bootstrap
- [`src/automana/worker/state.py`](../src/automana/worker/state.py) — `CeleryAppState` data object
- Pipeline definitions: [`src/automana/worker/tasks/pipelines.py`](../src/automana/worker/tasks/pipelines.py)

Redis is used as both broker and result backend.

### Developer tools

- **CLI**: `automana-run` ([`src/automana/tools/run_service.py`](../src/automana/tools/run_service.py)) — call any registered service from the command line
- **TUI**: `automana-tui` ([`src/automana/tools/tui/app.py`](../src/automana/tools/tui/app.py)) — terminal UI with tabs for services, Celery, and API testing

Both tools share the same bootstrap logic in [`src/automana/tools/tui/shared.py`](../src/automana/tools/tui/shared.py) and exercise the exact same code paths as production.

## Integrations

Integrations are exposed under `/api/integrations/...` and implemented via services.

Current integration areas include:

- **eBay** (OAuth + listing/search/selling)
- **Shopify** (metadata ingestion, market/collection/theme)
- **MTGStock** (staging/loading/pricing)
- **Scryfall** (daily ETL pipeline — see [`docs/SCRYFALL_PIPELINE.md`](SCRYFALL_PIPELINE.md))
- **MTGJson** (daily ETL pipeline)

The architecture pattern is:

```
API router / Celery task → ServiceManager → integration service → (DB repository + external API repository)
```

## Configuration

Runtime configuration is provided by Pydantic `BaseSettings` in [`src/automana/core/settings.py`](../src/automana/core/settings.py).

- The active environment is determined by `ENV` (default: `dev`).
- The settings loader reads: `config/env/.env.{ENV}` (with candidate path resolution for both project-root and installed-package layouts)
- Settings are cached via `@lru_cache` in `get_settings()`
- Secrets (JWT keys, PGP keys) are loaded from Docker secret files (`/run/secrets/`) with env-var fallback via [`src/automana/core/secrets.py`](../src/automana/core/secrets.py)
- Database passwords follow a cascade: explicit parameter > file path > env var > well-known file path

Important settings include:

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (composed into `DATABASE_URL_ASYNC`)
- `jwt_secret_key`, `pgp_secret_key`
- `MODULES_NAMESPACE` (which service modules to load)
- `DATA_DIR` (base path for file storage)
- `DISCORD_WEBHOOK_URL` (analytics notifications)

## Deployment

### Reverse proxy (nginx)

nginx is containerized and is the only component that should publish ports in production.

- Dockerfile: `deploy/docker/nginx/nginx.Dockerfile`

### Database backups

The prod compose includes a database backup container that:

- shares the internal `backend-network`
- runs `pg_dump` on a cron schedule
- writes dumps to a mounted folder

See: `deploy/docker-compose.prod.yml` (`db-backup-prod`).

## Adding new functionality (recommended pattern)

When adding a new feature:

1. Add/extend a service in `src/automana/core/services/...`
2. Decorate it with `@ServiceRegistry.register("dotted.service.key", db_repositories=[...], api_repositories=[...], storage_services=[...])`
3. If needed, register new repositories in [`src/automana/core/service_registry.py`](../src/automana/core/service_registry.py)
4. Add a thin router endpoint under `src/automana/api/routers/...`
5. Use `ApiResponse`/`PaginatedResponse` for consistency
6. Add/adjust schemas under `src/automana/core/models/` or `src/automana/api/schemas/`

## Non-negotiable rules

- **No direct DB access from routers** — all database access goes through the service layer
- **No `logging.basicConfig()`** — use `logging.getLogger(__name__)` everywhere; `configure_logging()` is called once at startup
- **No reserved `LogRecord` keys in `extra={}`** — use unambiguous names (e.g., `file` instead of `filename`)
- **No `autoretry_for` in pipeline tasks** — retry logic is handled at the `run_service` level
- **All config via `core/settings.py`** — no hardcoded credentials or paths
- **New schema changes need a migration** under `database/SQL/migrations/`

## Known sharp edges / follow-ups

- Some router modules contain TODO/incomplete endpoints; treat them as unstable API.
- The `AbstractRepository` base class has `print()` debug statements that should be replaced with `logger.debug()`.
- `pricing.load_price_observation_from_mtgjson_staging_batched` issues `COMMIT`/`ROLLBACK` inside its `WHILE` loop. Resolved by registering `staging.mtgjson.promote_to_price_observation` with `runs_in_transaction=False` (see "Per-service execution knobs" below).

## Per-service execution knobs

`ServiceRegistry.register` and `ServiceConfig` expose two optional knobs that
shape how `ServiceManager._execute_service` runs a call:

| Flag | Default | Effect |
|---|---|---|
| `runs_in_transaction` | `True` | `True` wraps the call in an explicit `BEGIN`/`COMMIT`. `False` gives the service a raw pool connection with no transaction started — required for services whose SQL manages its own transaction control (e.g. stored procs with internal `COMMIT`/`ROLLBACK`, which Postgres rejects when `CALL` is inside an atomic block). |
| `command_timeout` | `None` | Seconds. Applied server-side via `SET [LOCAL\|SESSION] statement_timeout`. `LOCAL` when inside a txn (auto-resets at COMMIT/ROLLBACK); `SESSION` when `runs_in_transaction=False` (explicit `RESET` on exit so pooled connections don't leak it). `None` keeps the role's `statement_timeout` GUC. |

Usage:

```python
@ServiceRegistry.register(
    "staging.mtgjson.promote_to_price_observation",
    db_repositories=["mtgjson"],
    runs_in_transaction=False,
    command_timeout=3600,
)
```

Both knobs default to today's behaviour; existing services need no changes.

