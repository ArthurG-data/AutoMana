
# AutoMana Architecture

This document explains how the backend is structured, how requests flow through the system, and where to add new features safely.

If you want the *exact* API surface, use `GET /docs` and `GET /openapi.json`.

## High-level overview

AutoMana is a FastAPI application backed by Postgres, with optional background processing via Celery/Redis, and a reverse proxy (nginx) in production.

### Layer Diagram

![Architecture Layers]diagrams/layer_diagramm.jpg

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

The FastAPI app is created in `backend/main.py`.

On startup (lifespan):

- Validates environment safety (database URL guard)
- Initializes an async DB pool (asyncpg) and a sync pool (psycopg2)
- Creates a `QueryExecutor`
- Initializes a singleton `ServiceManager` that dispatches service calls

On shutdown:

- Closes pools
- Closes the service manager

### Request flow (HTTP)

Typical request flow:

1. Client calls an endpoint under `/api/...`
2. Router function uses dependency injection to obtain:
	 - `ServiceManagerDep`
	 - optionally `CurrentUserDep` (auth)
	 - pagination/sort/search dependencies for list endpoints
3. Router calls `service_manager.execute_service("some.service.key", **kwargs)`
4. Service layer executes business logic using repositories
5. Response is wrapped in `ApiResponse`/`PaginatedResponse`

Key DI wiring lives in `backend/dependancies/service_deps.py`.

## Modules and responsibilities

### API layer (routing)

Routes are organized under `backend/api/`.

- Global API router: `backend/api/__init__.py` (prefix `/api`)
- Major areas:
	- Catalog: `/api/catalog/...`
	- Users/auth/sessions: `/api/users/...`
	- Integrations: `/api/integrations/...`
	- Logs: `/api/logs/...`

This layer should stay thin: validation, dependency wiring, and calling services.

### Service layer

The service layer lives under `backend/new_services/` and is orchestrated by `backend/new_services/service_manager.py`.

- The `ServiceManager` maintains a registry mapping a service key (string) to:
	- module path
	- function
	- required repositories
- Routers call `execute_service(...)` with a service key instead of importing the implementation directly.

This gives you a single place to:

- control dependencies
- reuse services from HTTP endpoints, Celery tasks, or workflows
- swap implementations without changing routers

### Repository/data access layer

Repositories live under `backend/repositories/` and related database utilities under `backend/database/`.

The backend uses:

- async DB access (asyncpg) for most service calls
- sync DB access (psycopg2) when needed

Pool initialization lives in `backend/core/database.py`.

### Standard response shapes

Standard response envelopes are defined in `backend/request_handling/StandardisedQueryResponse.py`:

- `ApiResponse`
- `PaginatedResponse`
- `ErrorResponse`

### Authentication & authorization

Current auth is cookie-based:

- A `session_id` cookie is used to identify the active session.
- The `CurrentUserDep` dependency resolves a user from the cookie.

Key file: `backend/dependancies/auth/users.py`.

### Background jobs (Celery)

Celery configuration and app wiring:

- `celery_app/celery_main_app.py`
- `celery_app/celeryconfig.py`
- tasks in `celery_app/tasks/` (e.g., scryfall/shopify/ebay)

Redis is typically used as broker/result backend (see env vars in config).

## Integrations

Integrations are exposed under `/api/integrations/...` and implemented via services.

Current integration areas include:

- eBay (OAuth + listing/search)
- Shopify (metadata ingestion)
- MTGStock (staging/loading)

The architecture pattern is:

API router -> ServiceManager -> integration service -> (DB repository + external API repository)

## Configuration

Runtime configuration is provided by Pydantic settings in `backend/core/settings.py`.

- The active environment is determined by `ENV` (default: `dev`).
- The settings loader reads: `config/env/.env.{ENV}`

Important variables typically include:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `PGP_SECRET_KEY`
- Celery broker/result backend variables

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

1. Add/extend a service in `backend/new_services/...`
2. Register it in `ServiceManager._service_registry`
3. Add a thin router endpoint under `backend/api/...`
4. Use `ApiResponse`/`PaginatedResponse` for consistency
5. Add/adjust schemas under `backend/schemas/...`

## Known sharp edges / follow-ups

- Some router modules contain TODO/incomplete endpoints; treat them as unstable API.

