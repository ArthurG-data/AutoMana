# Celery Worker: Switch to Prefork Pool

**Issue:** #327  
**Date:** 2026-05-30  
**Scope:** Worker pool config only — no code changes

## Problem

The celery-worker runs with `-P threads --concurrency=1` (hardcoded in `docker-compose.dev.yml`). Python threads cannot be killed individually — `app.control.revoke(terminate=True, signal='SIGTERM')` and `SIGKILL` have no effect on the active task. Stopping a runaway pipeline requires manually removing the task from the Redis `unacked` hash and restarting the container.

A contradiction also exists: `CELERY_POOL: "prefork"` is set as an env var in the dev compose but is never used because the command hardcodes `-P threads`.

The Dockerfile `CMD` defaults to `-P solo`, which is single-threaded and also not terminable per-task.

## Solution

Switch both the dev compose command and the Dockerfile `CMD` to use `-P prefork`. With prefork, each task runs in a forked subprocess — `revoke(terminate=True, signal='SIGTERM')` sends SIGTERM directly to that subprocess, stopping the task without touching the parent worker or requiring a container restart.

## Changes

### `deploy/docker-compose.dev.yml`

Replace hardcoded `-P threads` with `${CELERY_POOL:-prefork}` so the existing env var is honoured:

```yaml
command: >
  sh -c "celery -A automana.worker.main:app worker -P ${CELERY_POOL:-prefork}
  --loglevel=${CELERY_LOGLEVEL:-DEBUG}
  --concurrency=${CELERY_CONCURRENCY:-1}"
```

### `deploy/docker/celery/celery.Dockerfile`

Change the default `CMD` from `-P solo` to `-P prefork`:

```dockerfile
CMD ["celery", "-A", "automana.worker.main:app", "worker", "-P", "prefork", "--loglevel=INFO", "--concurrency=1"]
```

## What Does Not Change

- `celeryconfig.py` — unchanged
- All pipeline tasks and services — unchanged
- `concurrency=1` — unchanged (one task at a time, now in a subprocess instead of a thread)
- celery-beat — unchanged

## Verification

After rebuild + restart, confirm prefork is active:

```bash
docker exec automana-celery-dev celery -A automana.worker.main:app inspect stats | grep pool
```

Expected: `"pool": {"implementation": "celery.concurrency.prefork:TaskPool", ...}`

Then verify revoke terminates a running task:

```bash
# From Python inside the container
app.control.revoke('<task_id>', terminate=True, signal='SIGTERM')
# Task stops; worker process stays up
```

## Acceptance Criteria

- `celery inspect stats` reports prefork pool implementation
- `app.control.revoke(task_id, terminate=True, signal='SIGTERM')` stops an active task within a few seconds
- Worker container remains healthy after the revoke (parent process unaffected)
- `CELERY_POOL` env var in dev compose is now honoured by the command
