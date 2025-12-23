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

## Certificates

nginx mounts certs from `config/nginx/certs/`.

After updating certs on the host, restart the proxy:

```bash
docker compose -f deploy/docker-compose.prod.yml restart proxy
```
