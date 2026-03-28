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
- `app_integration/scryfall/` and `app_integration/mtgjson/` — ETL pipelines for card data
- `app_integration/ebay/` — eBay OAuth, browsing, buying, selling, analytics
- `app_integration/shopify/` — Shopify market, collection, theme
- `card_catalog/` — Core MTG card/set/collection operations
- `analytics/`, `auth/`, `user_management/`, `ops/`

**`src/automana/core/repositories/`** — All database queries. Organized to mirror the services layer. Use `QueryExecutor` (`core/QueryExecutor.py`) for async query execution with error handling.

**`src/automana/worker/`** — Celery tasks that reuse the same service layer. `ressources.py` handles async event loop and backend runtime initialization per worker. Beat schedule in `celeryconfig.py` runs daily Scryfall/MTGJson pipelines and analytics reports (timezone: Australia/Sydney).

**`src/automana/database/SQL/`** — SQL schemas (`01_set_schema.sql` through `11_staging_schema.sql`), migrations, ETL procedures, and analytics queries. Schema is applied via `infra/` init scripts.

### Key Patterns

- **Settings**: All config via Pydantic `BaseSettings` in `core/settings.py`; loaded from env vars or Docker secrets via `core/secrets.py`.
- **Database pools**: asyncpg for async paths (`core/database.py`), psycopg2 for sync/Celery paths.
- **Responses**: HTTP responses are wrapped in `ApiResponse` or `PaginatedResponse` (see `api/schemas/StandardisedQueryResponse.py`).
- **Logging**: Structured logging with request/task context tracking via `core/logging_context.py`.
- **Secrets**: Docker Compose mounts secret files from `config/secrets/`; `core/secrets.py` reads them at startup.

## Infrastructure

Dev stack ports: backend `8000`, postgres `5433`, redis `6379`, nginx `80/443`.
Production stack: only the nginx proxy is externally exposed.

Database schemas are versioned under `database/SQL/migrations/`. New schema changes need a corresponding migration file.
