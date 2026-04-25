# Operations (Runbook)

This runbook covers day-2 operations: checking health, viewing logs, restarting services, and database backup/restore.

For service layout and request flow, see `docs/ARCHITECTURE.md`. For endpoints, see `docs/API.md`.

## Quick checks

### Check containers and health

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

### Check the public entrypoint

Only nginx should be reachable from the network in prod.

```bash
curl -f http://localhost/health
curl -f https://localhost/health -k
```

### Confirm only proxy publishes ports

```bash
docker compose -f deploy/docker-compose.prod.yml config
```

You should see `ports:` only on the `proxy` service.

## Logs

### Follow logs for a single service

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f proxy
```

Other useful ones:

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f backend
docker compose -f deploy/docker-compose.prod.yml logs -f postgres
```

### Check nginx logs

nginx logs are inside the container at:

- `/var/log/nginx/access.log`
- `/var/log/nginx/error.log`

Quick view:

```bash
docker exec -it automana-proxy-prod sh -lc "tail -n 200 /var/log/nginx/error.log"
```

## Restarting safely

### Restart a single service

```bash
docker compose -f deploy/docker-compose.prod.yml restart backend
```

### Rebuild and restart (after changes)

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Database backups (prod)

Backups are produced by `db-backup-prod` and written to:

- host: `deploy/backups/prod/`
- container: `/backups`

### Check backups exist

```bash
ls deploy/backups/prod
```

### Trigger a manual backup (one-off)

Runs a single `pg_dump` into the same backup folder.

```bash
docker exec -it automana-postgres-prod sh -lc "pg_dump -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Fc -f /tmp/manual.dump" || true
```

Notes:
- The Postgres image may not have your env vars inside the container unless you pass them; the scheduled backup container is the canonical mechanism.

## Database restore (prod)

AutoMana backups are created with `pg_dump -Fc` (custom format). Restore uses `pg_restore`.

### Restore into an empty database (recommended workflow)

1) Stop services that talk to the DB:

```bash
docker compose -f deploy/docker-compose.prod.yml stop backend
```

2) Copy the dump file into the Postgres container (pick a dump filename):

```bash
# Example path; replace with your file
docker cp deploy/backups/prod/YOUR_DB_YYYYMMDD_HHMMSS.dump automana-postgres-prod:/tmp/restore.dump
```

3) Restore (drops/recreates objects; use with care):

```bash
docker exec -it automana-postgres-prod sh -lc "pg_restore -U app_prod -d manaforge_prod --clean --if-exists /tmp/restore.dump"
```

4) Start backend again:

```bash
docker compose -f deploy/docker-compose.prod.yml start backend
```

If your prod DB/user names differ, use the values from `config/env/.env.prod`.

## Flower (Celery monitoring)

Flower provides a real-time web UI for inspecting Celery workers and tasks.

### Access

Flower is only exposed through the nginx reverse proxy (not directly):

| Environment | URL | Auth |
|-------------|-----|------|
| Dev (proxy) | https://localhost/flower/ | `admin:changeme_dev` |
| Prod (proxy) | https://your-domain/flower/ | Via `FLOWER_BASIC_AUTH` (`.env.prod`) |

### Follow Flower logs

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f flower
```

### Restart Flower (without restarting other services)

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps flower
```

### Task history persistence

Flower persists task history to a SQLite database at `/data/flower.db` inside the container. This file is stored in a named Docker volume (`flower-data-dev` or `flower-data-prod`) and survives container restarts.

### Credential rotation

To update the Flower Basic Auth password:

1. Update `FLOWER_BASIC_AUTH` in the relevant env file (e.g. `config/env/.env.dev` or `config/env/.env.prod`).
2. Restart Flower:

```bash
# Dev
docker compose -f deploy/docker-compose.dev.yml up -d --no-deps flower

# Prod
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps flower
```

## Pipeline sanity checks

Three read-only SQL scripts provide structured post-run and periodic health checks for the Scryfall pipeline. They write nothing and can be re-run freely. All produce the same column shape: `check_name`, `severity`, `row_count`, `details`.

**Post-run diff** (run after every `scryfall_daily` execution):

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/scryfall_run_diff.sql
```

Surfaces run metadata, per-step status and timing, parsed `ProcessingStats` counters, and heuristic counts of sets and cards touched.

**Periodic integrity checks** (run daily or after manual data repairs):

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/scryfall_integrity_checks.sql
```

Runs 24 orphan/loose-data checks across `card_catalog`, `ops`, and `pricing` schemas. Any row with `severity = 'error'` warrants immediate investigation.

**Schema isolation check** (run after migrations or on a weekly CI schedule):

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/public_schema_leak_check.sql
```

Confirms that no application objects have leaked into the `public` schema.

For the full check catalogue, severity definitions, recommended cadence, and interpretation notes, see the [Sanity Checks & Maintenance Scripts](SCRYFALL_PIPELINE.md#sanity-checks--maintenance-scripts) section of `docs/SCRYFALL_PIPELINE.md`.

---

## Security

### Security headers

nginx adds the following security headers to all responses on port 443:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HSTS)
- `X-Frame-Options: SAMEORIGIN` (clickjacking protection)
- `X-Content-Type-Options: nosniff` (MIME type sniffing prevention)
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` (configured per route)

These are defined in `nginx.local.conf` and `nginx.prod.conf`.

### Certificates

nginx mounts certs from `config/nginx/certs/`.

After updating certs on the host, restart the proxy:

```bash
docker compose -f deploy/docker-compose.prod.yml restart proxy
```

## Service healthchecks

All services in docker-compose.dev.yml have healthchecks configured:

| Service | Check method | Notes |
|---------|--------------|-------|
| `backend` | `python3 urllib.request.urlopen('http://localhost:8000/health')` | Direct to backend |
| `postgres` | `pg_isready -U admin -d automana` | Database ready probe |
| `redis` | `redis-cli ping` | Cache ready probe |
| `proxy` | `wget -qO- --no-check-certificate https://localhost/health` | Reverse proxy ready; uses wget (curl not available) |
| `celery-beat` | `test -f /tmp/celerybeat.pid && kill -0 $(cat /tmp/celerybeat.pid)` | Process alive check |
| `celery-worker` | `celery -A automana.worker.main:app inspect ping` | Worker responds to inspect |
| `flower` | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:5555/healthcheck')"` | Flower endpoint |

All services except `schema-spy` have `restart: unless-stopped` configured.
