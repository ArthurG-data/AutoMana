# AutoMana

AutoMana is a FastAPI backend for tracking Magic: The Gathering card collections with integrations for eBay, Shopify, Scryfall, MTGJson, and MTGStock. It uses PostgreSQL (+ TimescaleDB + pgvector) for persistence, Redis for caching/queuing, and Celery for background jobs.

**Requires:** Python >= 3.11, Docker Compose v2.

## Documentation

Full documentation index: [docs/README.md](docs/README.md)

| Doc | Contents |
|-----|----------|
| [docs/API.md](docs/API.md) | Endpoint reference, auth model, response envelopes |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layer diagram, request flow (HTTP + Celery), module map |
| [docs/DESIGN_PATTERNS.md](docs/DESIGN_PATTERNS.md) | Every design pattern used, with file locations and rationale |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker Compose (dev/prod), env vars, nginx, TLS, Flower |
| [docs/LOGGING.md](docs/LOGGING.md) | Structured JSON logging, context vars, conventions |
| [docs/SCRYFALL_PIPELINE.md](docs/SCRYFALL_PIPELINE.md) | Scryfall ETL pipeline |
| [docs/MTGJSON_PIPELINE.md](docs/MTGJSON_PIPELINE.md) | MTGJson daily price ingestion pipeline |
| [docs/MTGSTOCK_PIPELINE.md](docs/MTGSTOCK_PIPELINE.md) | MTGStocks price ingestion pipeline |
| [docs/METRICS_REGISTRY.md](docs/METRICS_REGISTRY.md) | MetricRegistry and sanity-report runner |
| [docs/HEALTH_METRICS.md](docs/HEALTH_METRICS.md) | card_catalog and pricing health metrics |
| [docs/DATABASE_ROLES.md](docs/DATABASE_ROLES.md) | PostgreSQL roles and per-service DB users |
| [docs/CLI_RUN_SERVICE.md](docs/CLI_RUN_SERVICE.md) | `automana-run` CLI and `automana-tui` terminal UI |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Day-2 runbook: logs, restarts, backup/restore |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and fixes |

## Quickstart (Docker)

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- `docker compose` v2
- Environment file at `config/env/.env.dev` (start from `config/env/.env.example`)
- TLS certificates at `config/nginx/certs/` for HTTPS

### Dev

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

Access points:

| Service | URL | Notes |
|---------|-----|-------|
| API (direct) | http://localhost:8000 | Swagger UI at `/docs` |
| API (via proxy) | https://localhost/api/ | nginx reverse proxy with HTTPS |
| Health check | http://localhost:8000/health | Returns `{"status":"healthy"}` |
| Flower (Celery UI) | https://localhost/flower/ | Task monitoring; auth via `FLOWER_BASIC_AUTH` |
| Postgres | localhost:5433 | Host-side access (published port) |
| Redis | localhost:6379 | Host-side access (published port) |

Inside Docker Compose: Postgres is at `postgres:5432` and Redis is at `redis:6379` over the internal `backend-network`.

### Prod

Only the nginx proxy publishes ports (80/443). Backend, Postgres, and Redis are network-internal.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for TLS cert setup, required env vars, and the database backup container.

## Common Development Commands

### Docker Compose

```bash
# Start full stack (build if needed)
docker compose -f deploy/docker-compose.dev.yml up -d --build

# Start only Postgres and Redis
docker compose -f deploy/docker-compose.dev.yml up -d postgres redis

# Stop all services
docker compose -f deploy/docker-compose.dev.yml down

# Restart Celery workers
docker compose -f deploy/docker-compose.dev.yml restart celery-worker celery-beat

# Tail logs
docker compose -f deploy/docker-compose.dev.yml logs -f celery-worker
```

### Health & Status

```bash
# Check API health
curl http://localhost:8000/health

# Access Swagger UI
curl http://localhost:8000/docs

# Check Celery worker status
docker exec -it automana-celery-dev celery -A automana.worker.main:app inspect active
```

### Celery Tasks

```bash
# Ping the worker
docker exec -it automana-celery-dev celery -A automana.worker.main:app call ping

# Trigger a pipeline manually
docker exec -it automana-celery-dev celery -A automana.worker.main:app call daily_scryfall_data_pipeline

# Purge all queued tasks
docker exec -it automana-celery-dev celery -A automana.worker.main:app purge -f
```

### Running Services Manually (without Docker)

```bash
# Install as editable package (includes CLI tools)
pip install -e .

# Start API server
uvicorn automana.api.main:app --host 0.0.0.0 --port 8000

# Start Celery worker
celery -A automana.worker.main:app worker -P solo --loglevel=DEBUG

# Start Celery Beat scheduler
celery -A automana.worker.main:app beat --loglevel=INFO
```

## Testing

```bash
# Run all unit tests (default, fastest)
pytest

# Run unit tests only
pytest -m unit

# Run integration tests (requires Docker Postgres + Redis)
pytest -m integration

# Run API tests
pytest -m api

# Run with coverage
pytest --cov=src/automana --cov-report=html
```

Test markers:
- `unit` — No DB, no HTTP, no Redis
- `integration` — Real DB, real Redis, mocked HTTP boundaries
- `api` — Full-stack router + service + repository tests
- `repository` — Database-only tests
- `service` — Service-layer tests
- `pipeline` — Celery pipeline chain tests
- `slow` — Expected to run >10s (excluded by default)

See `pytest.ini` for test configuration.

## CLI Tools

Two console-script entry points are installed with `pip install -e .`:

### `automana-run` — Service CLI

Call any registered service from the command line without starting the full API server. Outputs JSON.

```bash
# List all registered services
automana-run --list

# Run a specific service
automana-run staging.scryfall.start_pipeline --ingestion_run_id=null

# Run with arguments
automana-run catalog.search_cards --query="Lightning Bolt"
```

See [docs/CLI_RUN_SERVICE.md](docs/CLI_RUN_SERVICE.md) for full usage, environment setup, and examples.

### `automana-tui` — Interactive Terminal UI

Terminal UI with tabs for services, Celery monitoring, and API testing. Shares the same bootstrap as `automana-run`.

```bash
automana-tui
```

## Database Rebuild (After Schema Changes)

When you modify the database schema, use the two-phase rebuild sequence to avoid stale asyncpg pool connections. This applies when Celery is running.

```bash
# Phase 1: Stop Celery, rebuild DB
dcdev-automana down
dcdev-automana up -d --build postgres redis
# Wait for Postgres to be healthy
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --only rebuild

# Phase 2: Restart Celery, run pipelines
dcdev-automana up -d --build celery-worker celery-beat
# Wait for Celery to be healthy
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --skip-rebuild
```

**Flags:**
- `--only rebuild` — Drops + creates + rebuilds schemas + grants. Exits immediately (does not require Celery).
- `--skip-rebuild` — Runs Scryfall → MTGStock → MTGJson pipelines and verifies via `ops.ingestion_runs`.

**Notes:**
- `down` removes containers but preserves bind mounts (`/data/postgres`, `/data/mtgjson`, etc.).
- MTGStock download reads from disk; data must exist at `/data/automana_data/mtgstocks/raw/prints/`.
- The `pricing.load_staging_prices_batched` procedure pre-creates required objects so it works under app_celery's restricted grant.

## Architecture

Strict layered architecture:

```
API Router → ServiceManager → Services → Repositories → Database
```

**Layers:**

- **Routers** (`src/automana/api/routers/`) — thin validation + DI; call `service_manager.execute_service()`
- **ServiceManager** (`src/automana/core/service_manager.py`) — singleton dispatcher; handles transactions and repository injection
- **Services** (`src/automana/core/services/`) — business logic; registered via `@ServiceRegistry.register("dotted.key", db_repositories=[...])`
- **Repositories** (`src/automana/core/repositories/`) — all DB and external API access; never called directly from routers
- **Celery** (`src/automana/worker/`) — same service and repository layers; async-to-sync via thread-confined event loop

**Key principle:** The HTTP request path and the Celery pipeline path use the same service layer and repositories. The `run_service` task dispatches any registered service by string key.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for layer diagram, full request flow, and module mapping.

## API Overview

All routes live under `/api`.

| Area | Base path | Key endpoints |
|------|-----------|---------------|
| Auth | `/api/users/auth` | `POST /token`, `POST /logout`, `POST /token/refresh` |
| Users | `/api/users/users` | CRUD, role assignment |
| Sessions | `/api/users/session` | Get, search, deactivate |
| Card reference | `/api/catalog/mtg/card-reference` | Search, suggest (fuzzy), CRUD, bulk insert |
| Collections | `/api/catalog/mtg/collection` | CRUD (requires session) |
| Set reference | `/api/catalog/mtg/set-reference` | Search, CRUD, bulk insert |
| eBay | `/api/integrations/ebay` | OAuth, listing create/update/history |
| Shopify | `/api/integrations/shopify` | Data load/stage, market/theme/collection metadata |
| MTGStock | `/api/integrations/mtg_stock` | Stage, load IDs, price load |
| Ops integrity | `/api/ops/integrity` | Run-diff, integrity checks, public schema audit |

**Auth:** Session cookie (`session_id`, httponly) for browsers; `Authorization: Bearer <jwt>` for programmatic clients. The `secure` flag is active on the session cookie in all non-dev environments.

For the full endpoint list, see [docs/API.md](docs/API.md) or the live Swagger UI at `GET /docs`.

## Configuration

All configuration comes from `src/automana/core/settings.py` (Pydantic `BaseSettings`) via environment variables or Docker secrets — no hardcoded credentials or paths.

**Active environment:** Set via the `ENV` env var (default: `dev`). Settings are cached via `@lru_cache`.

**Environment files:**

- `config/env/.env.dev`
- `config/env/.env.prod`
- `config/env/.env.example` (template)

Start from `.env.example` and fill required values.

**Key variables:**

| Variable | Purpose | Example |
|----------|---------|---------|
| `ENV` | Active environment | `dev`, `prod` |
| `POSTGRES_HOST` | Postgres hostname | `postgres` (Docker) or `localhost` |
| `POSTGRES_PORT` | Postgres port | `5432` (Docker) or `5433` (host) |
| `DB_NAME` | Database name | `automana` |
| `APP_BACKEND_DB_USER` | Backend app DB user | `app_backend` |
| `APP_CELERY_DB_USER` | Celery worker DB user | `app_celery` |
| `DB_PASSWORD` | DB password file path | `/run/secrets/backend_db_password` |
| `BROKER_URL` | Redis/Celery broker URL | `redis://redis:6379/0` |
| `MODULES_NAMESPACE` | Service loader scope | `backend`, `celery` |
| `DATA_DIR` | Data directory for exports/downloads | `/data` |
| `ALLOW_DESTRUCTIVE_ENDPOINTS` | Enable drop/delete endpoints (dev only) | `false` |
| `FLOWER_BASIC_AUTH` | Celery Flower auth | `user:password` |

See `config/env/.env.example` for the complete list and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for Docker secrets handling.

## Repository Structure

```
src/automana/
  api/              FastAPI app, routers, schemas
    routers/        Route handlers (users, catalog, integrations, ops)
    dependancies/   Dependency injection (DI)
    schemas/        Request/response Pydantic models
    request_handling/
    services/       (API-specific services, if any)
    repositories/   (API-specific repos, if any)
    utils/          Utility functions
  core/             Service layer, repositories, settings, logging
    services/       Business logic (registered via @ServiceRegistry.register)
    repositories/   DB (asyncpg/psycopg2) and external API clients
    metrics/        MetricRegistry for metrics collection
    settings.py     Configuration (Pydantic BaseSettings + @lru_cache)
    logging_config.py
    logging_context.py
    exceptions/     Custom exceptions
    models/         Data models
    schemas/        Data schemas
  worker/           Celery app, tasks, pipelines
    tasks/          Pipeline definitions (Scryfall, MTGJson, MTGStock, analytics)
    main.py         Celery app initialization
    logging/        Worker-specific logging
  database/
    SQL/
      schemas/      DDL (card_catalog, pricing, users, ebay, shopify, ops, etc.)
      migrations/   Incremental migration files
      maintenance/  rebuild_dev_db.sh and utility scripts
  tools/
    run_service.py  automana-run CLI
    tui/            automana-tui terminal UI
agentic_workflows/  LangGraph-based AI SQL agent (experimental)
config/
  env/              Environment files (.env.dev, .env.prod, .env.example)
  secrets/          Docker secrets (not committed; gitignored)
  nginx/            nginx proxy config and TLS certs
deploy/
  docker/           Dockerfiles
    backend/
    celery/
    postgres/
    nginx/
    schemaspy/
  docker-compose.dev.yml
  docker-compose.prod.yml
docs/               Full documentation
tests/              Unit and integration tests
  unit/
  integration/
.github/            Issue templates (workflows not yet set up)
```

## Database Schema Overview

AutoMana uses PostgreSQL with TimescaleDB extensions and pgvector for semantic search.

**Main schemas:**

| Schema | Purpose | Key tables |
|--------|---------|-----------|
| `card_catalog` | MTG cards and sets | `unique_cards_ref`, `card_version`, `set_reference`, `language_ref` |
| `pricing` | Price observations and rollups | `price_observation`, `print_price_daily`, `print_price_weekly`, `raw_mtg_stock_price`, `mtg_card_products` |
| `users` | User accounts, auth, roles | `user_account`, `user_role_assignment` |
| `ebay` | eBay integration state | `ebay_credential`, `ebay_listing_activity` |
| `shopify` | Shopify integration staging | Various staging tables |
| `mtgjson_staging` | MTGJson ingestion staging | Staging tables for daily price feeds |
| `ops` | Pipeline operations tracking | `ingestion_runs`, `ingestion_steps` |

**TimescaleDB hypertables:**
- `pricing.price_observation` — time-series fact table (7-day chunk interval, compressed after 180 days)

See `src/automana/database/SQL/schemas/` for complete DDL and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for database initialization.

## Data Pipelines

Three main ETL pipelines run via Celery Beat:

### Scryfall Pipeline
Ingests MTG card catalogue from Scryfall. Runs daily. Populates `card_catalog` schema.
→ See [docs/SCRYFALL_PIPELINE.md](docs/SCRYFALL_PIPELINE.md)

### MTGJson Pipeline
Ingests daily price aggregates from MTGJson. Runs daily. Populates `pricing` schema.
→ See [docs/MTGJSON_PIPELINE.md](docs/MTGJSON_PIPELINE.md)

### MTGStock Pipeline
Ingests price data from MTGStocks (4-stage: raw → resolve → retry → fact). Requires pre-scraped data on disk. Runs on-demand.
→ See [docs/MTGSTOCK_PIPELINE.md](docs/MTGSTOCK_PIPELINE.md)

All pipelines:
- Use `async with track_step(ops_repository, run_id, "step_name")` for step-level tracking
- Chain via Celery's `chain()` using `run_service.s(service_key, **kwargs)`
- Log structured JSON via `logger.info("msg", extra={...})`
- Write operational state to `ops.ingestion_runs` and `ops.ingestion_steps`

## Development Workflow

### 1. Install Dependencies

```bash
pip install -e ".[dev]"
```

This installs AutoMana in editable mode plus dev dependencies (pytest, pytest-asyncio, pytest-mock, pytest-cov).

### 2. Start Docker Stack

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

### 3. Run Tests

```bash
# Unit tests (default, no Docker needed)
pytest

# Integration tests (Docker Postgres + Redis required)
pytest tests/integration/

# Specific test
pytest tests/unit/core/test_settings.py::test_settings_load
```

### 4. Develop

- **Modify code** in `src/automana/`
- **Modify docs** in `docs/` — always read the relevant doc before modifying a subsystem (see [CLAUDE.md](CLAUDE.md) for the mapping)
- **Add migrations** to `src/automana/database/SQL/migrations/` for schema changes
- **Register new services** via `@ServiceRegistry.register("dotted.key", db_repositories=[...])`

### 5. Logs

```bash
# Tail container logs
docker compose -f deploy/docker-compose.dev.yml logs -f backend

# Inside a container
docker exec -it automana-backend-dev tail -f /var/log/automana/app.log
```

See [docs/LOGGING.md](docs/LOGGING.md) for structured logging setup and [docs/OPERATIONS.md](docs/OPERATIONS.md) for troubleshooting.

## Key Design Principles

From [CLAUDE.md](CLAUDE.md):

- **Strict layering:** Routers never touch the database directly; all DB access is through the service and repository layers.
- **No `logging.basicConfig()` in worker code** — use `logging.getLogger(__name__)`; `configure_logging()` is called once at startup.
- **Structured logging:** Keep message strings static; put all context in `extra={}` so fields appear discrete in JSON output.
- **Pipeline retry logic** at the `run_service` level, not with `autoretry_for`.
- **Pipeline step tracking** via `async with track_step(...)`, not manual `ops_repository.update_run()` calls.
- **Context key matching:** Keys returned by a pipeline step must match the parameter names of the next step.
- **All config from `core/settings.py`** via env vars or Docker secrets — no hardcoded credentials or paths.
- **Migrations required** for schema changes — new files under `database/SQL/migrations/`.

## Deployment

### Local (Dev)

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

### Production

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for:
- TLS certificate setup
- Environment file configuration
- Database backup container setup
- Postgres database initialization
- Database roles and permissions

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues:
- Connection errors
- Celery task failures
- Database migration issues
- Authentication problems
- Pipeline data validation

## Maintainer Notes

1. **Read the relevant doc before modifying a subsystem** — see the mapping in [CLAUDE.md](CLAUDE.md).
2. **Always write migrations** for schema changes; never modify existing schema files.
3. **Service layer never calls services directly** — always go through `ServiceManager.execute_service()` or Celery chains.
4. **Celery pool gotcha** — never restart Celery while running `rebuild_dev_db.sh` without the two-phase sequence.
5. **Flower authentication** — set `FLOWER_BASIC_AUTH` in env files for production.
6. **Never commit `.env` files or secrets** — all secrets go in `config/secrets/` (gitignored).

## Contributing

When adding a new feature:

1. Create or update a feature branch from `main`.
2. Write tests in `tests/` (unit, integration, or both as appropriate).
3. Follow the layered architecture (router → service → repository → DB).
4. Register new services via `@ServiceRegistry.register()`.
5. Add migrations if you modify the database schema.
6. Update relevant docs in `docs/`.
7. Submit a pull request.

See [docs/TESTING_API_FLOW.md](docs/TESTING_API_FLOW.md) for manual API testing (create user, auth, test, cleanup).

## License

(No license information found in repository — add if applicable.)

## Contact

For questions, refer to the documentation in `docs/` or contact the team at [insert contact info].
