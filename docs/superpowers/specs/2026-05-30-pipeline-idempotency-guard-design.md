# Pipeline Idempotency Guard Design

**Issue:** #326  
**Date:** 2026-05-30  
**Scope:** Long-running data pipeline tasks only

## Problem

When `celery-beat` fires a pipeline task while the worker is down, multiple copies accumulate in the Redis queue. On 2026-05-30, 4 duplicate `mtgStock_download_pipeline` entries were found alongside an already-running instance. There is no guard preventing a pipeline from starting if one is already running or has already succeeded today.

## Solution

Add an idempotency check at the entry point of each long-running pipeline task. Before dispatching the Celery chain, the task queries `ops.ingestion_runs` for a row matching today's `run_key`. If status is `running` or `success`, the task logs a warning and returns immediately without dispatching the chain.

`failed` is intentionally not blocked — a failed pipeline should be allowed to re-run.

## Affected Pipelines

The following 6 tasks in `src/automana/worker/tasks/pipelines.py` get the guard:

| Task | `run_key` format |
|------|-----------------|
| `daily_scryfall_data_pipeline` | `scryfall_daily:YYYY-MM-DD` |
| `mtgStock_download_pipeline` | `mtgStock_All:YYYY-MM-DD` |
| `daily_mtgjson_data_pipeline` | `mtgjson_daily:YYYY-MM-DD` |
| `daily_mtgjson_sealed_pipeline` | `mtgjson_sealed:YYYY-MM-DD` |
| `open_tcg_pricing_pipeline` | `opentcg_pricing:YYYY-MM-DD` |
| `shopify_weekly_pipeline` | `shopify_weekly:YYYY-MM-DD` |

`pipeline_health_alert_task`, `log_analysis_daily_task`, and `run_scryfall_integrity_checks` are excluded — they are lightweight, idempotent by nature, and do not write to `ops.ingestion_runs`.

## Architecture

### 1. Repository — `OpsRepository.get_run_status_for_key`

**File:** `src/automana/core/repositories/ops/ops_repository.py`

New method (pure read, `get_*` prefix per CQS rules):

```python
async def get_run_status_for_key(self, run_key: str) -> str | None:
```

Queries `ops.ingestion_runs` for the most recent row with the given `run_key`. Returns the `status` string (`'running'`, `'success'`, or `'failed'`) or `None` if no row exists.

### 2. Service — `is_run_active`

**File:** `src/automana/core/services/ops/pipeline_services.py`

New service registered as `"ops.pipeline_services.is_run_active"`:

```python
async def is_run_active(ops_repository: OpsRepository, run_key: str) -> dict:
```

Calls `get_run_status_for_key`. Returns `{"is_active": True}` if status is `running` or `success`, otherwise `{"is_active": False}`.

### 3. Guard in pipeline tasks

**File:** `src/automana/worker/tasks/pipelines.py`

Pattern added to each of the 6 pipeline tasks, after `run_key` is built and before `wf = chain(...)`:

```python
result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
if result.get("is_active"):
    logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
    return
```

## Behaviour

| Queue state | DB state | Outcome |
|-------------|----------|---------|
| 4 copies queued, none running | No row for today's key | First copy runs normally; copies 2–4 see `running` and skip |
| 1 copy queued | Today's run already `success` | Skipped immediately |
| 1 copy queued | Today's run `failed` | Runs normally (re-run allowed) |
| 1 copy queued | No row | Runs normally |

## Files Changed

| File | Change |
|------|--------|
| `src/automana/core/repositories/ops/ops_repository.py` | Add `get_run_status_for_key` |
| `src/automana/core/services/ops/pipeline_services.py` | Add `is_run_active` service |
| `src/automana/worker/tasks/pipelines.py` | Add guard to 6 pipeline tasks |

## Acceptance Criteria

- Firing any of the 6 pipeline tasks while one is already `running` or `success` for today's `run_key` results in a warning log and immediate return — no chain dispatched
- A `failed` run for today's `run_key` does not block a re-run
- No duplicate rows appear in `ops.ingestion_runs` for the same `run_key`
- `pipeline_health_alert_task`, `log_analysis_daily_task`, and `run_scryfall_integrity_checks` are unaffected
