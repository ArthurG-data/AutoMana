
# Deployment

This document explains how to run AutoMana locally and in production using the Docker Compose files in `deploy/`.

If you’re looking for endpoints, see `docs/API.md`. If you’re looking for component structure and request flow, see `docs/ARCHITECTURE.md`.

Related docs:

- `docs/OPERATIONS.md` (runbook: logs, restarts, backup/restore)
- `docs/TROUBLESHOOTING.md` (common issues and fixes)

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- `docker compose` v2
- A copy of your environment files under `config/env/`
- TLS certs for nginx under `config/nginx/certs/` (for HTTPS)

## Environment configuration

### Env files

The backend settings loader reads `ENV` and then loads:

- `config/env/.env.{ENV}`

Example env files:

- `config/env/.env.dev`
- `config/env/.env.staging`
- `config/env/.env.prod`

Start from `config/env/.env.example` and fill the required values (notably `DATABASE_URL`).

### Database URL

The backend expects `DATABASE_URL` in the form:

```
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB
```

In Docker Compose, `HOST` should be the **service name** (for example `postgres`).

## Local development (Docker Compose)

Compose file: `deploy/docker-compose.dev.yml`

What it does:

- `backend` publishes `8000:8000`
- `postgres` publishes `5433:5432` (convenience for local tools)
- `redis` publishes `6379:6379`
- `proxy` publishes `80:80` and `443:443`

Run:

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

Verify:

```bash
curl -f http://localhost:8000/health
curl -f https://localhost/health -k
```

Docs:

- Direct backend: `http://localhost:8000/docs`
- Through proxy: `https://localhost/docs` (may require `-k` for self-signed certs)

Stop:

```bash
docker compose -f deploy/docker-compose.dev.yml down
```

## Production (Docker Compose)

Compose file: `deploy/docker-compose.prod.yml`

Production goal:

- Only the `proxy` service is reachable from the network.
- `backend`, `postgres`, and `redis` are **internal-only** on Docker networks.

### 1) Prepare env

Fill `config/env/.env.prod`.

Minimum expected values include:

- `ENV=prod`
- `DATABASE_URL` (with host `postgres`)
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (used by the Postgres container)
- `JWT_SECRET_KEY` / `PGP_SECRET_KEY` (if used by your auth/encryption paths)
- `BACKUP_CRON` (used by `db-backup-prod`)

### 2) Prepare TLS certs

The nginx container mounts certs from:

- `config/nginx/certs/` -> `/etc/nginx/certs`

The current nginx config references:

- `/etc/nginx/certs/localhost.pem`
- `/etc/nginx/certs/localhost-key.pem`

For real production, replace these with valid certs and update the nginx config accordingly.

### 3) Start the stack

From the repo root:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

### 4) Verify

Check container health:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

Check the proxy is serving:

```bash
curl -f http://localhost/health
curl -f https://localhost/health -k
```

Confirm only the proxy publishes ports:

```bash
docker compose -f deploy/docker-compose.prod.yml config
```

You should see `ports:` only under the `proxy` service.

### Stop / remove

```bash
docker compose -f deploy/docker-compose.prod.yml down
```

To also remove volumes (DANGER: deletes DB data):

```bash
docker compose -f deploy/docker-compose.prod.yml down -v
```

## Database initialization

On first Postgres startup (empty volume), initialization scripts are mounted from:

- `infra/db/init/` -> `/docker-entrypoint-initdb.d/`

Examples include:

- enabling extensions (TimescaleDB + pgvector)
- creating runtime roles for `app_dev`, `app_test`, `app_prod`

Important: these init scripts run **only the first time** the database volume is created.

## Backups (prod)

In `deploy/docker-compose.prod.yml`, the `db-backup-prod` container:

- connects to Postgres over the internal Docker network
- runs `pg_dump` on a cron schedule (`BACKUP_CRON`)
- writes `.dump` files to:
	- host: `deploy/backups/prod/`
	- container: `/backups`

Notes:

- Ensure `BACKUP_CRON` is set (cron format). Example: `0 2 * * *` (02:00 daily).
- The current script keeps the 6 most recent dumps (older ones are deleted).

## Nginx reverse proxy

Nginx is built from:

- `deploy/docker/nginx/nginx.Dockerfile`

The nginx image selects the config at build time via a build arg:

- dev uses `nginx.local.conf` (wired in `deploy/docker-compose.dev.yml`)
- prod uses `nginx.prod.conf` (wired in `deploy/docker-compose.prod.yml`)

## Operational notes / caveats

- The backend container currently starts uvicorn with `--reload` (see `deploy/docker/backend/Backend.Dockerfile`). For production you usually want to remove `--reload`.
- Cookie security flags in auth routes may be set to `secure=False` in code; in production behind HTTPS, you typically want `Secure` cookies.
- Celery configuration currently loads a dev env file in `celery_app/celeryconfig.py`. If you deploy Celery for prod, align it with `ENV=prod` and your prod env file.

