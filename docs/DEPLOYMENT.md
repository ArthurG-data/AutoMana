
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

Start from `config/env/.env.example` and fill the required values.

### Database connection

The backend composes its connection URL from individual env vars (not a single `DATABASE_URL` string):

| Env var | Alias in settings | Default | Purpose |
|---------|-------------------|---------|---------|
| `POSTGRES_HOST` | `DB_HOST` | `localhost` | Postgres host |
| `POSTGRES_PORT` | `DB_PORT` | `5432` | Postgres port |
| `DB_NAME` | `DB_NAME` | `automana` | Database name |
| `APP_BACKEND_DB_USER` | `DB_USER` | `app_backend` | Application DB user |
| `DB_PASSWORD` | (cascade) | — | Password (file path, env var, or well-known path) |

In Docker Compose, `POSTGRES_HOST` is overridden to the service name (`postgres`) in the `environment:` block of the `backend` and `celery-*` services. Host-side tools (e.g., psql, pgAdmin) use `localhost:5433` (the published port in dev).

## Local development (Docker Compose)

Compose file: `deploy/docker-compose.dev.yml`

What it does:

- `backend` publishes `8000:8000`
- `postgres` publishes `5433:5432` (convenience for local tools)
- `redis` publishes `6379:6379`
- `proxy` publishes `80:80`, `443:443`, and `8080:8080`
- `flower` is not directly exposed (only via nginx proxy)
- `frpc` tunnels external traffic to `proxy:8080` via the VPS relay (see [VPS tunnel relay](#vps-tunnel-relay) below)

Run:

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

Verify:

```bash
curl -f http://localhost:8000/health
curl -f https://localhost/health -k
```

Service access:

| Service | URL | Notes |
|---------|-----|-------|
| Backend API | `http://localhost:8000` | Direct; also exposed through proxy |
| Backend API (proxy) | `https://localhost/api/` | Through nginx reverse proxy (HTTPS) |
| Backend API (tunnel) | `http://localhost:8080/api/` | Through nginx port 8080 — HTTP basic auth required |
| OpenAPI docs | `https://localhost/docs` | Through nginx reverse proxy |
| Health check | `https://localhost/health` | Through nginx reverse proxy; `/health` on port 8080 is auth-exempt |
| Flower | `https://localhost/flower/` | Through nginx proxy (443 and 8080); auth: `admin:changeme_dev` (from `FLOWER_BASIC_AUTH`) |
| Postgres | `localhost:5433` | Host-side access (`.env.dev` default); containers use `postgres:5432` |
| Redis | `localhost:6379` | Host-side access; containers use `redis:6379` |

### Container environment overrides

The `backend` and `celery-beat` services override `POSTGRES_HOST` and `POSTGRES_PORT` in their `environment:` blocks:

```yaml
environment:
  POSTGRES_HOST: postgres
  POSTGRES_PORT: 5432
```

This overrides `.env.dev`'s `localhost:5433` (which is for host-side tools only). Inside the Docker network, containers reach Postgres via the service name `postgres` on port `5432`.

Stop:

```bash
docker compose -f deploy/docker-compose.dev.yml down
```

### ngrok tunnel setup

The dev stack includes an `ngrok` container that exposes the app to the internet through nginx port 8080 for eBay OAuth callbacks and external testing.

**How it works:**

- nginx port 8080 listens as a plain-HTTP tunnel endpoint; it sets `X-Forwarded-Proto: https` so the app sees HTTPS even though the upstream connection is plain HTTP.
- HTTP basic auth is enforced on all requests to port 8080 (except `/health`). Credentials are stored in `config/nginx/htpasswd` (gitignored).
- Flower gets a dedicated `limit_req_zone` on both 443 and 8080 (5 r/m, burst 3), separate from the general per-IP zone.
- Security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, CSP) are present on the 8080 block. HSTS is intentionally absent (port 8080 is plain HTTP).

**Prerequisites:**

1. Set `NGROK_AUTHTOKEN` in `config/env/.env.dev`.
2. Create `config/nginx/htpasswd` from the example:
   ```bash
   # see config/nginx/htpasswd.example for the generation command
   cp config/nginx/htpasswd.example config/nginx/htpasswd
   # edit htpasswd and replace the placeholder hash with a real one
   ```
3. `config/nginx/htpasswd` is gitignored — never commit it.

The `ngrok` service in `deploy/docker-compose.dev.yml` connects to `proxy:8080` using a fixed free-tier domain (`--pooling-enabled` lets it rejoin if a terminal session already holds the domain).

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

### Proxy configuration

The nginx config defines per-location proxy settings:

| Location | Purpose | HTTP version | Timeouts |
|----------|---------|--------------|----------|
| `/health` | Backend health probe | 1.1 | 2s connect/send/read |
| `/api/` | Application API + WebSocket | 1.1 | 60s connect/send/read |
| `/flower/` | Celery task monitoring | 1.1 | 60s connect/send/read |
| `/docs` | OpenAPI documentation | 1.1 | (default 60s) |
| `/` | Catchall | 1.1 | (default 60s) |

**Key note:** All locations use `proxy_http_version 1.1` to enable the upstream connection keepalive pool (32 connections), which would be unused under HTTP/1.0. The `/health` location has short 2-second timeouts to prevent cascading proxy restarts when the backend hiccups (the Docker healthcheck has a 5-second timeout).

### Security headers

All responses on HTTPS (port 443) include:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HSTS)
- `X-Frame-Options: SAMEORIGIN` (clickjacking protection)
- `X-Content-Type-Options: nosniff` (MIME sniffing prevention)
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'`

Responses on the plain-HTTP tunnel (port 8080) include the same headers except HSTS (omitted deliberately — HSTS on a plain-HTTP port has no effect and can cause browser confusion).

## Flower (Celery monitoring)

Flower provides a real-time web UI for inspecting Celery workers and tasks.

### Access

Flower is only exposed through the nginx reverse proxy (not directly on port 5555):

| Environment | URL | Auth |
|-------------|-----|------|
| Dev (proxy HTTPS) | https://localhost/flower/ | `admin:changeme_dev` (from `FLOWER_BASIC_AUTH` in `.env.dev`) |
| Dev (tunnel HTTP) | http://localhost:8080/flower/ | HTTP basic auth (htpasswd) + `FLOWER_BASIC_AUTH` |
| Prod (proxy) | https://your-domain/flower/ | Configure via `FLOWER_BASIC_AUTH` in `.env.prod` |

### Persistence

Task history is persisted via a named Docker volume (`flower-data-dev` or `flower-data-prod`). The SQLite database is stored at `/home/appuser/flower/flower.db` inside the container.

### Environment variables

| Variable | Description |
|----------|-------------|
| `BROKER_URL` | Redis broker URL (e.g. `redis://redis:6379/0`) |
| `FLOWER_BASIC_AUTH` | HTTP Basic Auth credentials in `user:password` format (dev and prod) |

## Operational notes / caveats

- The backend container currently starts uvicorn with `--reload` (see `deploy/docker/backend/Backend.Dockerfile`). For production you usually want to remove `--reload`.
- Cookie `secure` flag is set dynamically: `True` in all environments except `dev` (`get_settings().env != "dev"`). In dev, cookies are sent over plain HTTP; in staging/prod (behind the nginx TLS terminator) the `Secure` flag is active automatically.
- Celery configuration lives at `src/automana/worker/celeryconfig.py`. The active env is determined by the `ENV` env var — ensure `ENV=prod` (and the corresponding `config/env/.env.prod`) is set when running Celery in production.

