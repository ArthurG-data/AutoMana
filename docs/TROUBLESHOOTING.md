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
