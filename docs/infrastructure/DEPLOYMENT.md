
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
| Backend API (tunnel) | `https://automana.duckdns.org/api/` | Via VPS relay → nginx:8080 — HTTP basic auth required |
| OpenAPI docs | `https://localhost/docs` | Through nginx reverse proxy |
| Health check | `https://localhost/health` | Through nginx reverse proxy; `/health` on port 8080 is auth-exempt |
| Health check (external) | `https://automana.duckdns.org/health` | Auth-exempt, no credentials needed |
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

The `backend` service also sets two additional vars that must be present for the eBay integration to work correctly:

| Env var | Required value (dev) | Purpose |
|---------|----------------------|---------|
| `REDIS_CACHE_URL` | `redis://redis:6379/1` | Redis URL for access-token cache (db 1). The settings alias is `REDIS_CACHE_URL` — using `REDIS_URL` will silently fall back to `localhost:6379` and break the OAuth callback. |
| `FRONTEND_BASE_URL` | `https://automana.duckdns.org` | Base URL the backend appends to OAuth callback redirects. Defaults to `http://localhost:5173` if unset — wrong in any tunnelled/deployed environment. |

Both are set in the `environment:` block of the `backend` service in `deploy/docker-compose.dev.yml`.

Stop:

```bash
docker compose -f deploy/docker-compose.dev.yml down
```

### VPS tunnel relay

The dev stack includes a `frpc` container that exposes the app to the internet through nginx port 8080 for eBay OAuth callbacks and external testing. Traffic flows:

```
https://automana.duckdns.org → Caddy (VPS, TLS) → frps (VPS) → frpc (local) → nginx:8080 → FastAPI
```

**How it works:**

- nginx port 8080 listens as a plain-HTTP tunnel endpoint; it sets `X-Forwarded-Proto: https` so the app sees HTTPS even though the upstream connection is plain HTTP.
- HTTP basic auth is enforced on all requests to port 8080 (except `/health`). Credentials are stored in `config/nginx/htpasswd` (gitignored).
- Flower gets a dedicated `limit_req_zone` on both 443 and 8080 (5 r/m, burst 3), separate from the general per-IP zone.
- Security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, CSP) are present on the 8080 block. HSTS is intentionally absent (port 8080 is plain HTTP).

**Prerequisites:**

1. Set `FRP_TOKEN` and `FRP_SERVER_ADDR` in `config/env/.env.dev`:
   ```bash
   FRP_TOKEN=<generate with: openssl rand -hex 32>
   FRP_SERVER_ADDR=103.6.171.115
   ```
2. Create `config/nginx/htpasswd` from the example:
   ```bash
   cp config/nginx/htpasswd.example config/nginx/htpasswd
   # edit htpasswd and replace the placeholder hash with a real one
   ```
3. `config/nginx/htpasswd` is gitignored — never commit it.

**VPS relay setup** (one-time, files in `deploy/vps/`):

1. Copy files to VPS: `scp -r deploy/vps/. root@103.6.171.115:~/automana-vps/`
2. Create `~/automana-vps/.env.vps` with the same `FRP_TOKEN`
3. Run firewall: `bash ~/automana-vps/setup-ufw.sh`
4. Start relay: `docker compose -f ~/automana-vps/docker-compose.vps.yml up -d`
5. Point `automana.duckdns.org` DNS A record to `103.6.171.115`

The VPS relay runs only frps + Caddy — no application data, no database.

## Production (Docker Compose)

Compose file: `deploy/docker-compose.prod.yml`

Production services:

| Service | Purpose | Networks |
|---------|---------|----------|
| `proxy` | nginx reverse proxy — the only service with published ports (80, 443) | `backend-network`, `frontend-network` |
| `backend` | FastAPI application | `backend-network` |
| `frontend` | React SPA (nginx, serves built assets) | `frontend-network` |
| `redis` | Celery broker + cache | `backend-network` |

Services **not in prod compose** (dev/local only): `postgres`, `celery-worker`, `celery-beat`, `flower`, `ollama`.

The database runs on the host machine (or a separate server) and is reachable by the backend container via the FRP TCP tunnel at `host.docker.internal:15432`.

### 1) Prepare env

Fill `config/env/.env.prod`.

Minimum expected values:

- `ENV=prod`
- `APP_BACKEND_DB_USER` — application DB username
- `POSTGRES_HOST` is overridden to `host.docker.internal` in compose; `POSTGRES_PORT` to `15432`
- `FRONTEND_BASE_URL=https://automana.duckdns.org`
- `REDIS_CACHE_URL=redis://redis:6379/1`

### 2) Prepare Docker secrets

Sensitive credentials are injected via Docker secrets (mounted at `/run/secrets/`) rather than env vars. Create these files before starting the stack:

```bash
mkdir -p config/secrets
echo "your-backend-db-password"  > config/secrets/backend_db_password.txt
echo "your-agent-db-password"    > config/secrets/agent_db_password.txt
openssl rand -hex 32             > config/secrets/jwt_secret_key.txt
openssl rand -hex 32             > config/secrets/pgp_secret_key.txt
```

| Secret | File | Consumed by |
|--------|------|-------------|
| `backend_db_password` | `config/secrets/backend_db_password.txt` | `$POSTGRES_PASSWORD_FILE` in backend |
| `agent_db_password` | `config/secrets/agent_db_password.txt` | `$AGENT_DB_PASSWORD_FILE` in backend |
| `jwt_secret_key` | `config/secrets/jwt_secret_key.txt` | JWT signing |
| `pgp_secret_key` | `config/secrets/pgp_secret_key.txt` | PGP encryption |

`config/secrets/` is gitignored — never commit these files.

### 3) Prepare TLS certs

The nginx prod config uses Let's Encrypt certificates mounted from the host:

- `/etc/letsencrypt` → `/etc/letsencrypt:ro`
- `/var/www/certbot` → `/var/www/certbot:ro`

The config expects certs at `/etc/letsencrypt/live/automana.duckdns.org/fullchain.pem` and `privkey.pem`. Obtain them with Certbot before starting nginx, or use the ACME challenge location at `/.well-known/acme-challenge/`.

### 4) Start the stack

From the repo root:

```bash
docker compose --env-file config/env/.env.prod -f deploy/docker-compose.prod.yml up -d --build
```

### 5) Verify

Check container health:

```bash
docker compose --env-file config/env/.env.prod -f deploy/docker-compose.prod.yml ps
```

Check the proxy is serving:

```bash
curl -f http://localhost/health
curl -f https://localhost/health -k
```

Confirm only the proxy publishes ports:

```bash
docker compose --env-file config/env/.env.prod -f deploy/docker-compose.prod.yml config
```

You should see `ports:` only under the `proxy` service.

### Stop / remove

```bash
docker compose --env-file config/env/.env.prod -f deploy/docker-compose.prod.yml down
```

## Backups (prod)

The `db-backup-prod` container was removed from `deploy/docker-compose.prod.yml` because the database runs externally (not as a Docker service). Run `pg_dump` from the host or a cron job connecting to the DB directly. See `CLAUDE.md` for the standard backup command.

## Nginx reverse proxy

Nginx is built from:

- `deploy/docker/nginx/nginx.Dockerfile`

The nginx image selects the config at build time via a build arg:

- dev uses `nginx.local.conf` (wired in `deploy/docker-compose.dev.yml`)
- prod uses `nginx.prod.conf` (wired in `deploy/docker-compose.prod.yml`)

### Proxy configuration

The nginx prod config (`nginx.prod.conf`) routes:

| Location | Upstream | Notes |
|----------|----------|-------|
| `/health` | `fastapi_backend` (backend:8000) | Health probe; access log off |
| `/api/` | `fastapi_backend` | WebSocket upgrade headers set; 60s timeouts |
| `/docs` | `fastapi_backend` | OpenAPI UI |
| `/flower/` | `flower:5555` (dynamic) | Dev-only — no `flower` service in prod compose; requests return 502 in prod |
| `/` | `frontend` (frontend:80) | React SPA fallback |

**Key note:** The `/flower/` location uses a variable-based `proxy_pass` so nginx starts without a `flower` container present. In prod, flower is not deployed — the location exists for optional re-enablement without nginx config changes.

### Security headers

All HTTPS (port 443) responses include:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HSTS)
- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https://cards.scryfall.io https://svgs.scryfall.io https://*.ebayimg.com data:;`

## Flower (Celery monitoring)

Flower is a **dev-only** service. It is not included in `deploy/docker-compose.prod.yml`.

In development, Flower is only exposed through nginx (not directly on port 5555):

| Environment | URL | Auth |
|-------------|-----|------|
| Dev (proxy HTTPS) | https://localhost/flower/ | `admin:changeme_dev` (from `FLOWER_BASIC_AUTH` in `.env.dev`) |
| Dev (tunnel HTTP) | http://localhost:8080/flower/ | HTTP basic auth (htpasswd) + `FLOWER_BASIC_AUTH` |

Task history is persisted via `flower-data-dev` Docker volume (SQLite at `/home/appuser/flower/flower.db`).

| Variable | Description |
|----------|-------------|
| `BROKER_URL` | Redis broker URL (e.g. `redis://redis:6379/0`) |
| `FLOWER_BASIC_AUTH` | HTTP Basic Auth credentials in `user:password` format |

## CI/CD

Two GitHub Actions workflows live in `.github/workflows/`:

### `ci.yml` — unit tests

Triggers on push to `dev` and on pull requests targeting `dev` or `main`.

Steps:
1. Check out code
2. Install dependencies via `uv sync --frozen --extra dev`
3. Run `pytest -v --tb=short` (unit tests only — integration tests require a live DB and are excluded via markers)

`POSTGRES_PASSWORD=ci-dummy` is set so `Settings` can be imported without a real DB.

### `deploy.yml` — test + deploy to VPS

Triggers on push to `main`.

Steps:
1. **test** job — same unit test run as `ci.yml`
2. **deploy** job (runs after `test` passes) — SSH into the VPS via `appleboy/ssh-action` and:
   - `git fetch origin && git checkout -B main origin/main`
   - `docker compose --env-file config/env/.env.prod -f deploy/docker-compose.prod.yml up -d --build --force-recreate`
   - Poll `https://${PROD_DOMAIN}/health` every 5s for up to 120s

Required GitHub secrets:

| Secret | Purpose |
|--------|---------|
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | SSH login username |
| `VPS_SSH_KEY` | Private SSH key |
| `PROD_DOMAIN` | Domain used for health-check polling (e.g. `automana.duckdns.org`) |

## Operational notes / caveats

- Cookie `secure` flag is set dynamically: `True` in all environments except `dev` (`get_settings().env != "dev"`). In dev, cookies are sent over plain HTTP; in staging/prod (behind the nginx TLS terminator) the `Secure` flag is active automatically.
- Celery workers and beat are **not in prod compose**. If background jobs are needed in prod, add celery-worker and celery-beat back to `deploy/docker-compose.prod.yml` following the dev compose pattern.
- Celery configuration lives at `src/automana/worker/celeryconfig.py`. The active env is determined by the `ENV` env var.

