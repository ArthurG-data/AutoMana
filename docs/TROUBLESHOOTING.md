# Troubleshooting

This page lists common deployment/runtime issues and fast checks.

## Docker Compose warnings about missing env vars

When running `docker compose ... config` you may see warnings like:

- `The "POSTGRES_USER" variable is not set. Defaulting to a blank string.`

This usually happens because Compose evaluates `${VARS}` in the YAML even when you intend to supply them via `env_file:` at runtime.

What to do:

- If the stack starts and the service reads values from `env_file`, you can often ignore these warnings.
- To silence warnings, export the vars in your shell before running `docker compose config`, or avoid `${...}` expansion in the compose file.

## nginx returns 502 Bad Gateway

Most common causes:

1) Upstream name mismatch (nginx proxies to a service name that doesn’t exist)
2) Backend container isn’t healthy / isn’t listening on port 8000

Checks:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
docker compose -f deploy/docker-compose.prod.yml logs --tail 200 proxy
docker compose -f deploy/docker-compose.prod.yml logs --tail 200 backend
```

Quick in-container check:

```bash
docker exec -it automana-proxy-prod sh -lc "wget -qO- http://backend:8000/health || true"
```

## Proxy healthcheck failing / proxy container repeatedly restarting

The nginx proxy container's healthcheck (`wget ... /health`) is timing out or failing.

Likely cause: Backend is slow or temporarily unresponsive. The nginx `/health` location has 2-second proxy timeouts (see `OPERATIONS.md` → "Service healthchecks"). If the backend takes longer, the healthcheck fails, and Docker restarts the proxy.

Checks:

```bash
# Check proxy healthcheck logs
docker compose -f deploy/docker-compose.dev.yml logs --tail 50 proxy

# Check backend health directly
curl http://localhost:8000/health

# Check backend logs for slowness
docker compose -f deploy/docker-compose.dev.yml logs --tail 100 backend
```

If the backend is slow:
- Check database connectivity: `docker compose -f deploy/docker-compose.dev.yml logs --tail 50 postgres`
- Verify asyncpg pool is initialized correctly (check `src/automana/core/database.py` pool settings)
- Ensure Redis is healthy: `docker compose -f deploy/docker-compose.dev.yml logs --tail 50 redis`

## HTTPS issues / browser warnings

Your default certs are mounted from `config/nginx/certs/` and may be self-signed.

- For curl, use `-k` to ignore trust issues.
- For production, install a real certificate and ensure nginx config references it.

## Backend fails on startup (DB connection)

Common root causes:

- `DATABASE_URL` host points to `localhost` instead of the compose service name `postgres`
- wrong credentials
- Postgres not healthy yet

Checks:

```bash
docker compose -f deploy/docker-compose.prod.yml logs --tail 200 postgres
docker compose -f deploy/docker-compose.prod.yml logs --tail 200 backend
```

Ensure `DATABASE_URL` (in `config/env/.env.prod`) uses `postgres` as host:

- ✅ `...@postgres:5432/...`
- ❌ `...@localhost:5432/...`

## InterfaceError during long-running batch operations (e.g., bulk_load)

Error: `InterfaceError: connection has been released back to the pool`

Likely cause: The database connection was silently closed by the OS TCP stack during a long idle window (e.g., 30-50s of CPU-heavy batch processing with no DB activity).

This is prevented by TCP keepalive settings configured in `src/automana/core/database.py`:
- `tcp_keepalives_idle`: 60s before first probe
- `tcp_keepalives_interval`: 10s between probes
- `tcp_keepalives_count`: 5 probes before giving up

If you still see this error:
- Ensure the asyncpg pool is reinitialized (pool is created once at app startup via `init_async_pool()`)
- Check that `max_inactive_connection_lifetime=3600` is set in the pool config
- Verify the backend container is not being restarted mid-operation

## Postgres init scripts did not run

The SQL scripts under `infra/db/init/` run only on the **first** startup when the DB volume is empty.

If you already have a volume, they will not re-run.

Options:

- Apply changes manually via `psql`, or
- Recreate the volume (DANGER: deletes data):

```bash
docker compose -f deploy/docker-compose.prod.yml down -v
```

## Backup container not producing dumps

Checks:

```bash
docker compose -f deploy/docker-compose.prod.yml logs --tail 200 db-backup-prod
```

Common causes:

- `BACKUP_CRON` not set or invalid cron expression
- wrong DB env vars (user/db/password)
- volume path permissions on host

## Sessions/auth failing (401)

AutoMana has two auth transports:

1. **Session cookie** — interactive/browser clients. The `session_id` cookie is `httponly` (not readable by JavaScript) and `samesite=strict`. After login, the cookie is set automatically by the browser or by curl with `-c`/`-b`.
2. **Bearer token** — programmatic callers. Pass `Authorization: Bearer <access_token>` in the request header. The token is returned in the JSON body of `POST /api/users/auth/token`. There is no `access_token` cookie.

If you are getting 401:

- Cookie clients: ensure your client keeps cookies and that the `session_id` cookie is present after login. In non-dev environments the cookie requires HTTPS (`secure` flag is set).
- Bearer clients: confirm you are reading `access_token` from the login JSON response and sending it as `Authorization: Bearer <token>`. Cookie fallback for JWT was removed.

See the examples in `docs/API.md`.

## Pipeline appears stuck (scryfall_daily)

The run shows `status = 'running'` but has not progressed in over 2 hours.

Check the `scryfall-runs-stuck-running` integrity check:

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/scryfall_integrity_checks.sql
```

Filter the output for `check_name = 'scryfall-runs-stuck-running'`. If `row_count > 0`, the `details` column lists the stuck run IDs, start times, and which step was last active. Cross-reference with Celery / Flower logs to confirm whether the worker process is still alive.

## Cards showing no artwork

Common causes:

- Illustrations exist in `card_catalog.illustrations` but are not linked to any card version or face row (`illustration-unreferenced`).
- Illustrations are linked but have a NULL `image_uris` column (`illustration-null-image-uris`).

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/scryfall_integrity_checks.sql
```

Filter the output for `check_name IN ('illustration-unreferenced', 'illustration-null-image-uris')`.

## New cards missing after a run

After a `scryfall_daily` run, expected cards are absent from `card_catalog`.

Common causes:

- The card's `set_id` could not be resolved during import and the card was routed to the MISSING_SET sentinel (`card-version-routed-to-missing-set`).
- The `card_version` row was written but the `unique_cards_ref` FK link is broken (`card-version-no-unique-card`).
- One or more pipeline steps failed, preventing the cards from being written (`last-run-failed-steps`).

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/scryfall_integrity_checks.sql
```

Filter for `check_name IN ('card-version-routed-to-missing-set', 'card-version-no-unique-card', 'last-run-failed-steps')`. Also run the post-run diff to review step-level counters:

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/scryfall_run_diff.sql
```

## Unexpected tables appearing in public schema

An unqualified `CREATE TABLE` during a migration or ad-hoc session may have placed objects in `public` instead of the intended schema.

```bash
psql "$DATABASE_URL" -f src/automana/database/SQL/maintenance/public_schema_leak_check.sql
```

Any row with `severity = 'error'` (`card-catalog-tables-in-public`) means the pipeline may have silently been reading or writing to the wrong schema. `severity = 'warn'` rows (`unexpected-tables-in-public`, `views-in-public`, `sequences-in-public`, `functions-in-public`) indicate leftover objects that should be dropped or moved. Drop the offending objects and re-run the check to confirm resolution.
