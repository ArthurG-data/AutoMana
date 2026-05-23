# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoMana is a FastAPI backend for tracking Magic: The Gathering card collections with integrations for eBay, Shopify, Scryfall, MTGJson, and MTGStock. It uses PostgreSQL (+ TimescaleDB + pgvector) for persistence, Redis for caching/queuing, and Celery for background jobs.

## Rules

- Always read the relevant `docs/` file before modifying a subsystem (see **Coding Guidelines** for the mapping).
- Never access the database directly from a router — all DB access goes through the service layer.
- Never use `logging.basicConfig()` or create custom log handlers in worker code. Use `logging.getLogger(__name__)` everywhere; `configure_logging()` is called once at process startup.
- Never pass reserved `LogRecord` attributes (`filename`, `module`, `lineno`, etc.) as keys in `extra={}`. Use unambiguous names (e.g. `file`, `batch`).
- Logging convention: keep the message string static; put all structured context in `extra={}` so it appears as discrete fields in the JSON payload. Never interpolate values into the message with `%s` or f-strings — use `logger.info("msg", extra={"key": value})` instead of `logger.info("msg %s", value)`.
- Pipeline tasks (`worker/tasks/pipelines.py`) must not use `autoretry_for` — retry logic is handled at the `run_service` level.
- Pipeline services must use `async with track_step(ops_repository, ingestion_run_id, "step_name")` for step-level ops tracking (see `docs/architecture/DESIGN_PATTERNS.md` §Pipeline Step Tracking). Never call `ops_repository.update_run(status="running"/"success"/"failed")` directly inside a service function — `track_step` handles the None guard, the running/success/failed lifecycle, and the `error_details` key format (`"message"`).
- Context keys returned by a pipeline step must exactly match the parameter names of the next step in the chain (the `run_service` dispatcher filters by signature).
- All config comes from `core/settings.py` via env vars or Docker secrets. No hardcoded credentials or paths.
- New schema changes require a migration file under `database/SQL/migrations/`.
- Git workflow: always open PRs against `dev`, never directly against `main`. Feature branches branch off `dev` and merge back into `dev`. Only `dev` merges into `main` for releases.
- Repository separation of concerns: when creating or registering a new service, each data-access concern must live in its own repository class — never mixed. Specifically: DB queries → an `AbstractDBRepository` subclass; external API calls → an `AbstractAPIRepository` subclass; file/storage I/O → a dedicated storage service. If a service needs more than one concern, wire multiple repositories via the `@ServiceRegistry.register` decorator (`db_repositories`, `api_repositories`, `storage_services`). A service that mixes DB queries and external HTTP in the same repository class violates this rule and must be refactored before merging.
- DB repository method naming enforces CQS (Command-Query Separation): methods that only read data and produce no side effects on the database must be named with a `get_*` / `fetch_*` / `list_*` / `exists_*` prefix (queries); methods that write, update, delete, or call a stored procedure that issues `COMMIT`/`ROLLBACK` must be named with an `insert_*` / `update_*` / `delete_*` / `upsert_*` / `execute_*` prefix (commands). If a method has any side effect on the database it is a command, regardless of whether it also returns data — use a command prefix.


## Coding Guidelines

| Area | Reference |
|------|-----------|
| API structure and endpoints | [`docs/api/API.md`](docs/api/API.md) |
| Layered architecture and patterns | [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) |
| Logging setup and usage | [`docs/infrastructure/LOGGING.md`](docs/infrastructure/LOGGING.md) |
| Scryfall ETL pipeline | [`docs/pipelines/SCRYFALL_PIPELINE.md`](docs/pipelines/SCRYFALL_PIPELINE.md) |
| MTGJson ETL pipeline | [`docs/pipelines/MTGJSON_PIPELINE.md`](docs/pipelines/MTGJSON_PIPELINE.md) |
| MTGStocks ETL pipeline | [`docs/pipelines/MTGSTOCK_PIPELINE.md`](docs/pipelines/MTGSTOCK_PIPELINE.md) |
| Shopify storefront integration | [`docs/backend/integrations/SHOPIFY_INTEGRATION.md`](docs/backend/integrations/SHOPIFY_INTEGRATION.md) |
| eBay global market scraper | [`docs/pipelines/EBAY_GLOBAL_MARKET_SCRAPER.md`](docs/pipelines/EBAY_GLOBAL_MARKET_SCRAPER.md) |
| Database roles and permissions | [`docs/infrastructure/DATABASE_ROLES.md`](docs/infrastructure/DATABASE_ROLES.md) |
| Deployment and Docker | [`docs/infrastructure/DEPLOYMENT.md`](docs/infrastructure/DEPLOYMENT.md) |
| Ops and monitoring | [`docs/operations/OPERATIONS.md`](docs/operations/OPERATIONS.md) |
| Running services via CLI or TUI | [`docs/operations/CLI_RUN_SERVICE.md`](docs/operations/CLI_RUN_SERVICE.md) |
| Troubleshooting | [`docs/operations/TROUBLESHOOTING.md`](docs/operations/TROUBLESHOOTING.md) |
| Design patterns lexicon | [`docs/architecture/DESIGN_PATTERNS.md`](docs/architecture/DESIGN_PATTERNS.md) |
| MetricRegistry and sanity reports | [`docs/operations/METRICS_REGISTRY.md`](docs/operations/METRICS_REGISTRY.md) |
| Database health metrics (card_catalog.*, pricing.*) and the on-demand scryfall audit | [`docs/operations/HEALTH_METRICS.md`](docs/operations/HEALTH_METRICS.md) |
| Manual API testing flow (create user, auth, test, cleanup) | [`docs/testing/TESTING_API_FLOW.md`](docs/testing/TESTING_API_FLOW.md) |
| React SPA (design system, routing, stores, MSW, testing) | [`docs/frontend/FRONTEND.md`](docs/frontend/FRONTEND.md) |
| API layer bugs and technical debt backlog | [`docs/api/API_LAYER_BACKLOG.md`](docs/api/API_LAYER_BACKLOG.md) |
| Consolidated technical debt backlog (all layers) | [`docs/MASTER_TECHNICAL_DEBT.md`](docs/MASTER_TECHNICAL_DEBT.md) |

## Common Commands

For common commands, see `.claude/common_commands.md`.

## Database Dumps — Backup Before Rebuild

Before running `rebuild_dev_db.sh` (without `--preserve-data`), always create a backup dump of the current database state:

```bash
# Dump the entire automana database
docker exec automana-postgres-dev pg_dump -U automana_admin automana | gzip > backups/automana-$(date -u +%Y%m%d-%H%M%S).sql.gz

# To restore from backup later:
docker exec -i automana-postgres-dev psql -U automana_admin automana < backups/automana-YYYYMMDD-HHMMSS.sql
```

This prevents loss of pricing data, pipeline progress, and testing work during development.

## Full dev rebuild — the bullet-proof sequence

`rebuild_dev_db.sh` runs `pg_terminate_backend` then `DROP DATABASE`. If celery is up at that moment, its asyncpg pool keeps stale connections and every subsequent task fails with `ConnectionDoesNotExistError`. The fix is a two-phase startup so celery's pool only ever sees the post-rebuild DB:

**OPTION A (Safe):** Use `--preserve-data` to skip DROP DATABASE and keep all work:

```bash
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --preserve-data
```

This applies schemas + migrations incrementally without destroying pricing data or pipeline progress.

**OPTION B (Full rebuild):** If you need a clean slate, create a dump first, then rebuild:

```bash
# 1. Backup the database
docker exec automana-postgres-dev pg_dump -U automana_admin automana | gzip > backups/automana-$(date -u +%Y%m%d-%H%M%S).sql.gz

# 2. Full rebuild with two-phase startup (keeps celery pool clean)
dcdev-automana down
dcdev-automana up -d --build postgres redis
# wait postgres healthy
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --only rebuild
dcdev-automana up -d --build celery-worker celery-beat
# wait celery healthy
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --skip-rebuild
```

Notes:
- `down` only removes containers; bind mounts (`/data/postgres`, `/data/automana_data/mtgstocks/raw/prints`, `/data/mtgjson`) survive.
- `--only rebuild` does DROP + CREATE + schemas + grants and exits — its preflight does not require celery.
- `--preserve-data` applies schemas + migrations without DROP — use when you want to keep pricing data and work-in-progress.
- `--skip-rebuild` runs scryfall → mtgstock → mtgjson → verify, polling `ops.ingestion_runs` for terminal status.
- `mtgStock_download_pipeline` reads from disk; it does not download. The data must already exist at `/data/automana_data/mtgstocks/raw/prints/`.
- The `pricing.load_staging_prices_batched` procedure does runtime DDL; the schema files now pre-create the required objects (`stg_price_observation_reject`, `stg_price_obs_date_spid_foil_idx`) so the procedure's IF NOT EXISTS clauses no-op under app_celery's USAGE-only grant.

## Architecture

Strict layered architecture: **API Router → ServiceManager → Services → Repositories → Database**

See [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) for layer responsibilities, request flow (HTTP and Celery), key patterns, and the full module map.

Dev stack ports: backend `8000`, postgres `5433`, redis `6379`, nginx `80/443/8080` (8080 is the ngrok tunnel listener). See [`docs/infrastructure/DEPLOYMENT.md`](docs/infrastructure/DEPLOYMENT.md) for infrastructure setup.
