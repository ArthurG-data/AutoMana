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

The API uses a cookie named `session_id` for authenticated routes.

Checks:

- Ensure your client keeps cookies (browser does; curl must use `-c`/`-b`).
- Confirm the `session_id` cookie is present after login.

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
