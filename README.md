# AutoMana

AutoMana is a FastAPI backend for tracking a Magic: The Gathering collection with integrations for eBay, Shopify, Scryfall, MTGJson, and MTGStock. It uses PostgreSQL (+ TimescaleDB + pgvector) for persistence, Redis for caching/queuing, and Celery for background jobs.

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

### Dev

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

| Service | URL | Notes |
|---------|-----|-------|
| API (direct) | http://localhost:8000 | Swagger UI at `/docs` |
| API (proxy) | https://localhost/api/ | Via nginx, HTTPS |
| Swagger UI | https://localhost/docs | Via nginx |
| Health | http://localhost:8000/health | Returns `{"status":"healthy"}` |
| Flower | https://localhost/flower/ | Celery task monitor; auth from `FLOWER_BASIC_AUTH` |
| Postgres | localhost:5433 | Host-side access only |
| Redis | localhost:6379 | Host-side access only |

Ports `80`/`443` on the proxy and `8000` on the backend are published in dev. Containers reach Postgres at `postgres:5432` over the internal Docker network.

### Prod

Only nginx publishes ports (80/443). The backend, Postgres, and Redis are network-internal.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for TLS cert setup, env var requirements, and the database backup container.

## Dev rebuild (after DB schema changes)

If you need to drop and recreate the dev database while Celery is running, follow the two-phase sequence to avoid stale asyncpg pool connections:

```bash
dcdev-automana down
dcdev-automana up -d --build postgres redis
# wait for postgres to be healthy
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --only rebuild
dcdev-automana up -d --build celery-worker celery-beat
# wait for celery to be healthy
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --skip-rebuild
```

`--only rebuild`: DROP + CREATE + schemas + grants, then exits.
`--skip-rebuild`: runs Scryfall -> MTGStock -> MTGJson pipelines and verifies via `ops.ingestion_runs`.

## Architecture

Strict layered architecture:

```
API Router -> ServiceManager -> Services -> Repositories -> Database
```

- **Routers** (`src/automana/api/routers/`) — thin: validation, DI, call `service_manager.execute_service()`
- **ServiceManager** (`src/automana/core/service_manager.py`) — singleton dispatcher; handles transactions, repository injection, service registry lookup
- **Services** (`src/automana/core/services/`) — business logic; registered via `@ServiceRegistry.register("dotted.key", db_repositories=[...])` decorator
- **Repositories** (`src/automana/core/repositories/`) — all DB and external API access; never called from routers directly
- **Celery** (`src/automana/worker/`) — same service layer, same repositories, bridged async-to-sync via a thread-confined event loop

The HTTP path and the Celery pipeline path go through identical code. The `run_service` task dispatches any registered service by string key.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full layer diagram and request flow.

## API overview

All routes live under the `/api` prefix.

| Area | Base path | Key endpoints |
|------|-----------|---------------|
| Auth | `/api/users/auth` | `POST /token` (login), `POST /logout`, `POST /token/refresh` |
| Users | `/api/users/users` | CRUD, role assignment |
| Sessions | `/api/users/session` | Get / search / deactivate |
| Card reference | `/api/catalog/mtg/card-reference` | Search, suggest (fuzzy), CRUD, bulk insert |
| Collections | `/api/catalog/mtg/collection` | CRUD (requires session) |
| Set reference | `/api/catalog/mtg/set-reference` | Search, CRUD, bulk insert |
| eBay | `/api/integrations/ebay` | OAuth, listing create/update/history |
| Shopify | `/api/integrations/shopify` | Data load/stage, market/theme/collection meta |
| MTGStock | `/api/integrations/mtg_stock` | Stage, load IDs, price load |
| Ops integrity | `/api/ops/integrity` | Scryfall run-diff, integrity checks, public-schema-leak check |

Auth uses a split-transport model: session cookie (`session_id`, httponly) for browser clients; `Authorization: Bearer <jwt>` for programmatic callers. The `secure` flag on the session cookie is active in all non-dev environments.

For the full endpoint list see [docs/API.md](docs/API.md) or the live Swagger UI at `/docs`.

## Developer tools

Two tools ship as console-script entry points (installed via `pip install -e .`):

- **`automana-run`** — call any registered service from the CLI without starting the full API server. Boots the same DB pool and `ServiceManager` as production and prints the result as JSON.
- **`automana-tui`** — terminal UI with tabs for services, Celery, and API testing. Shares the same bootstrap as `automana-run`.

```bash
# Install entry points
pip install -e .

# List all registered services
automana-run --list

# Run a specific service
automana-run staging.scryfall.start_pipeline --ingestion_run_id=null
```

See [docs/CLI_RUN_SERVICE.md](docs/CLI_RUN_SERVICE.md) for full usage, prerequisites, and examples.

## Repo layout

```
src/automana/
  api/              — FastAPI app, routers, schemas, request handling
    routers/
      users/        — auth, session, users
      catalog/      — MTG card reference, collections, set reference
      integrations/ — eBay, Shopify, MTGStock
      ops/          — integrity checks
  core/             — service layer, repositories, settings, logging, metrics
    services/       — business logic (registered via @ServiceRegistry.register)
    repositories/   — DB (asyncpg/psycopg2) and external API clients
    metrics/        — MetricRegistry for sanity-report metrics
  worker/           — Celery app, run_service task, pipeline definitions
    tasks/          — pipeline chains (Scryfall, MTGJson, MTGStock, analytics)
  database/
    SQL/
      schemas/      — DDL for all schemas
      migrations/   — incremental migration files
      maintenance/  — rebuild scripts
  tools/
    run_service.py  — automana-run CLI
    tui/            — automana-tui terminal UI
agentic_workflows/  — LangGraph-based AI SQL agent
config/
  env/              — .env.dev, .env.prod, .env.example, ...
  secrets/          — Docker secret files (not committed)
deploy/             — Docker Compose files and Dockerfiles
docs/               — documentation
tests/              — unit and integration tests
```

## Configuration

All config comes from `src/automana/core/settings.py` (Pydantic `BaseSettings`) via env vars or Docker secrets — no hardcoded credentials or paths. The active environment is set by the `ENV` env var (default: `dev`). Settings are cached via `@lru_cache`.

Key vars: `POSTGRES_HOST`, `POSTGRES_PORT`, `DB_NAME`, `APP_BACKEND_DB_USER`, `DB_PASSWORD`, `BROKER_URL`, `ENV`, `MODULES_NAMESPACE`, `DATA_DIR`.

See `config/env/.env.example` for the full list.
