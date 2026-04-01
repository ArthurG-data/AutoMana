# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoMana is a FastAPI backend for tracking Magic: The Gathering card collections with integrations for eBay, Shopify, Scryfall, MTGJson, and MTGStock. It uses PostgreSQL (+ TimescaleDB + pgvector) for persistence, Redis for caching/queuing, and Celery for background jobs.

## Common Commands

### Development with Docker (recommended)
```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
docker compose -f deploy/docker-compose.dev.yml down
curl http://localhost:8000/health
curl http://localhost:8000/docs   # Swagger UI
```

### Running services manually
```bash
pip install -e .
uvicorn automana.api.main:app --host 0.0.0.0 --port 8000
celery -A automana.worker.main:app worker
celery -A automana.worker.main:app beat
```

### Tests
```bash
pytest
pytest -m unit
pytest -m integration
pytest -m api
pytest -m repository
pytest -m service
```

Test markers are defined in `pytest.ini`; testpath is `tests/`.

## Architecture

The codebase uses a strict layered architecture: **API Router → ServiceManager → Services → Repositories → Database**

### Layer Responsibilities

**`src/automana/api/`** — HTTP layer only. Routers inject dependencies (ServiceManager, CurrentUser, pagination) and call `service_manager.execute_service("dotted.path.key", **kwargs)`. Routers never access the database directly.

**`src/automana/core/service_manager.py`** — Singleton that resolves service keys (registered via `service_registry.py`) and dispatches calls. This is the shared execution context for both HTTP requests and Celery tasks.

**`src/automana/core/services/`** — Business logic, organized by domain:
- `app_integration/scryfall/` — ETL pipeline for Scryfall card/set data (see Scryfall Pipeline below)
- `app_integration/mtgjson/` — ETL pipeline for MTGJson card data
- `app_integration/ebay/` — eBay OAuth, browsing, buying, selling, analytics
- `app_integration/shopify/` — Shopify market, collection, theme
- `card_catalog/` — Core MTG card/set/collection operations
- `analytics/`, `auth/`, `user_management/`, `ops/`

**`src/automana/core/repositories/`** — All database queries. Organized to mirror the services layer. Use `QueryExecutor` (`core/QueryExecutor.py`) for async query execution with error handling.

**`src/automana/worker/`** — Celery tasks that reuse the same service layer. `ressources.py` handles async event loop and backend runtime initialization per worker. Beat schedule in `celeryconfig.py` runs daily Scryfall (08:08 AEST) and MTGJson (09:08 AEST) pipelines, plus analytics (11:00 AEST). Tasks use `autoretry_for=(Exception,)` with exponential backoff.

**`src/automana/database/SQL/`** — SQL schemas (`01_set_schema.sql` through `11_staging_schema.sql`), migrations, ETL procedures, and analytics queries. Schema is applied via `infra/` init scripts.

### Key Patterns

- **Settings**: All config via Pydantic `BaseSettings` in `core/settings.py`; loaded from env vars or Docker secrets via `core/secrets.py`.
- **Database pools**: asyncpg for async paths (`core/database.py`), psycopg2 for sync/Celery paths.
- **Responses**: HTTP responses are wrapped in `ApiResponse` or `PaginatedResponse` (see `api/schemas/StandardisedQueryResponse.py`).
- **Logging**: Structured logging with request/task context tracking via `core/logging_context.py`.
- **Secrets**: Docker Compose mounts secret files from `config/secrets/`; `core/secrets.py` reads them at startup.

## Scryfall Pipeline

Daily Celery chain (`daily_scryfall_data_pipeline`) defined in `worker/tasks/pipelines.py`. Steps run in order via `chain()`:

| Step | Service key | What it does |
|------|-------------|--------------|
| 1 | `staging.scryfall.start_pipeline` | Creates an ops run record, returns `ingestion_run_id` |
| 2 | `staging.scryfall.get_bulk_data_uri` | Reads the Scryfall bulk manifest URI from the DB |
| 3 | `staging.scryfall.download_bulk_manifests` | Fetches the manifest JSON from the Scryfall API |
| 4 | `staging.scryfall.update_data_uri_in_ops_repository` | Diffs URIs against DB; returns only changed URIs to download |
| 5 | `staging.scryfall.download_sets` | Downloads sets JSON (skips if today's file already exists) |
| 6 | `card_catalog.set.process_large_sets_json` | Loads sets into the DB |
| 7 | `staging.scryfall.download_cards_bulk` | Stream-downloads card bulk JSON (skips if no URI changes) |
| 8 | `card_catalog.card.process_large_json` | Loads cards into the DB |
| 9 | `ops.pipeline_services.finish_run` | Marks the run as success |
| 10 | `staging.scryfall.delete_old_scryfall_folders` | Keeps the 3 most recent files, deletes older ones |

**File naming convention**: downloaded bulk files are saved as `{run_id}_{YYYYMMDD}_{original_filename}` (e.g. `42_20240315_default-cards.json`). The cleanup step matches files with glob `*default-card*` and sorts by the date token at position 1 of the `_`-split filename.

**Storage**: `StorageService` (`core/storage.py`) wraps `LocalStorageBackend`. `list_directory(pattern)` passes the glob pattern to `fnmatch` for filtering. `StorageService` instances are injected via `storage_services=["scryfall"]` in the `@ServiceRegistry.register` decorator.

## Infrastructure

Dev stack ports: backend `8000`, postgres `5433`, redis `6379`, nginx `80/443`.
Production stack: only the nginx proxy is externally exposed.

Database schemas are versioned under `database/SQL/migrations/`. New schema changes need a corresponding migration file.
