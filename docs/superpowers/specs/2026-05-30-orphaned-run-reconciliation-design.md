# Orphaned Ingestion Run Reconciliation on Worker Startup

**Issue:** #329  
**Date:** 2026-05-30  
**Scope:** `OpsRepository`, `pipeline_services.py`, `worker/main.py`

## Problem

After a system crash, `ops.ingestion_runs` rows with `status = 'running'` are left open indefinitely. On 2026-05-30, run `mtgStock_All:2026-05-25` (id=30) showed `failed` in the DB while the corresponding `run_service` Celery task was still executing — meaning the DB status and actual execution state were decoupled. Any `running` row from before a crash is an orphan: no live task will ever call `finish_run` or `fail_run` to close it.

## Solution

Add a `worker_ready` signal handler that, at worker startup, finds all `running` ingestion runs and marks them `failed` with `error_code = 'orphaned_by_restart'`. Since the worker just started, no legitimate running tasks exist yet — every `running` row is stale.

## Architecture

Three-layer change following existing project patterns:

### 1. Repository — `get_running_ingestion_runs`

**File:** `src/automana/core/repositories/ops/ops_repository.py`

```python
async def get_running_ingestion_runs(self) -> list[dict]:
```

Pure read (`get_*` CQS). Returns all rows from `ops.ingestion_runs WHERE status = 'running'` as `[{"id": int, "pipeline_name": str, "run_key": str}]`.

### 2. Service — `reconcile_orphaned_runs`

**File:** `src/automana/core/services/ops/pipeline_services.py`

Registered as `"ops.pipeline_services.reconcile_orphaned_runs"` with `db_repositories=["ops"]`.

```python
async def reconcile_orphaned_runs(ops_repository: OpsRepository) -> dict:
```

Calls `get_running_ingestion_runs()`. For each row, calls:
```python
await ops_repository.fail_run(
    row["id"],
    error_code="orphaned_by_restart",
    error_details={"message": "Worker restarted while run was in progress"},
)
```

Returns `{"reconciled": N, "runs": [{"id": ..., "pipeline_name": ..., "run_key": ...}]}`.

### 3. Worker signal — `_reconcile_orphaned_runs`

**File:** `src/automana/worker/main.py`

New `worker_ready` handler (second handler, independent of `_purge_stale_beat_tasks`):

```python
@worker_ready.connect
def _reconcile_orphaned_runs(sender, **_):
    result = run_service("ops.pipeline_services.reconcile_orphaned_runs")
    if result.get("reconciled", 0) > 0:
        logger.warning(
            "Orphaned ingestion runs closed on startup",
            extra={"reconciled_runs": result["runs"]}
        )
```

`run_service(...)` is called directly (not `.delay()`) — same pattern as `pipeline_health_alert_task`. The DB pool and service manager are ready because `worker_process_init` fires before `worker_ready`.

## Ordering Guarantee

```
worker_process_init → init_backend_runtime() → DB pool + service manager ready
        ↓
worker_ready → _purge_stale_beat_tasks (queue cleanup)
             → _reconcile_orphaned_runs (DB reconciliation)
```

## Behaviour

| State | Outcome |
|-------|---------|
| 3 `running` rows after crash | All 3 marked `failed`, warning logged with run details |
| 0 `running` rows | No-op, no log |
| Fresh start (never crashed) | No-op, no log |

## Technical Debt — Multi-Worker Caveat

This design assumes a **single Celery worker**. Marking all `running` rows as `failed` on startup is only safe because there is only one worker — there is no other worker that might legitimately have a task in flight.

**If multiple workers are ever introduced**, this reconciliation must be updated to:
1. Inspect active tasks across all workers via `celery inspect active`
2. Only mark a run `failed` if its `celery_task_id` is not in any worker's active set

Track this in the technical debt backlog: `docs/MASTER_TECHNICAL_DEBT.md`.

## Files Changed

| File | Change |
|------|--------|
| `src/automana/core/repositories/ops/ops_repository.py` | Add `get_running_ingestion_runs` |
| `src/automana/core/services/ops/pipeline_services.py` | Add `reconcile_orphaned_runs` service |
| `src/automana/worker/main.py` | Add `_reconcile_orphaned_runs` worker_ready handler |

## Acceptance Criteria

- After a worker restart with orphaned `running` rows, all are marked `failed` with `error_code='orphaned_by_restart'`
- A WARNING log lists the closed runs by id, pipeline_name, run_key
- If no orphaned runs exist, no log is emitted
- `is_run_active` (from #326) returns `False` for runs closed by this reconciliation
