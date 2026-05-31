# Queue Bloat Auto-Purge on Worker Startup

**Issue:** #328  
**Date:** 2026-05-30  
**Scope:** `src/automana/worker/main.py` only

## Problem

After a prolonged outage (e.g. 5-day crash on 2026-05-30), beat-sourced tasks accumulate in the Redis queue — one copy per missed firing interval. On restart, 1339 stale tasks were found: 1181 `drain_listing_actions_task` (every 5 min), 9 `pipeline_health_alert_task`, and 5 copies each of several daily pipelines. These had to be manually purged. No automatic mechanism exists.

## Solution

Add a `worker_ready` signal handler in `src/automana/worker/main.py` that runs once when the Celery worker is ready to accept tasks. It scans the Redis queue, identifies beat-sourced tasks with more than 1 copy, keeps exactly 1, and removes the rest.

## Beat Fingerprints

A "beat fingerprint" uniquely identifies a task as beat-sourced. It is derived at startup from `celeryconfig.beat_schedule`:

- For non-`run_service` tasks: the task name alone, e.g. `("automana.worker.tasks.ebay_actions.drain_listing_actions_task",)`
- For `run_service` tasks (which are beat-sourced but share a name): the task name plus the `path` kwarg, e.g. `("run_service", "ops.integrity.pricing_report")`

Current `run_service` beat paths (6):
- `ops.integrity.card_catalog_report`
- `ops.integrity.pricing_report`
- `integrations.ebay.promote_sold_obs`
- `integrations.pricing.fetch_fx_rates`
- `integrations.ebay.refresh_scrape_targets`
- `integrations.ebay.scrape_global_market`

`run_service` tasks with any other `path` (e.g. `mtg_stock.data_staging.bulk_load`, `ops.pipeline_services.start_run`) are pipeline chain steps and are **never purged**.

## Implementation

**File:** `src/automana/worker/main.py`

Add a `worker_ready` signal handler:

```python
import base64, json
import redis as redis_lib
from celery.signals import worker_ready
from automana.worker.celeryconfig import beat_schedule

def _build_beat_fingerprints():
    fps = set()
    for entry in beat_schedule.values():
        task = entry["task"]
        if task == "run_service":
            path = entry.get("kwargs", {}).get("path")
            if path:
                fps.add(("run_service", path))
        else:
            fps.add((task,))
    return fps

def _task_fingerprint(raw: bytes):
    msg = json.loads(raw)
    task_name = msg.get("headers", {}).get("task")
    if not task_name:
        return None
    if task_name == "run_service":
        body = json.loads(base64.b64decode(msg["body"]))
        # body = [args, kwargs, options]; beat tasks put path in kwargs
        kwargs = body[1] if isinstance(body, list) and len(body) > 1 else {}
        path = kwargs.get("path") if isinstance(kwargs, dict) else None
        return ("run_service", path) if path else None
    return (task_name,)

@worker_ready.connect
def _purge_stale_beat_tasks(sender, **_):
    beat_fingerprints = _build_beat_fingerprints()
    r = redis_lib.from_url(sender.app.conf.broker_url)
    raw_items = r.lrange("celery", 0, -1)

    groups: dict[tuple, list[bytes]] = {}
    for raw in raw_items:
        try:
            fp = _task_fingerprint(raw)
            if fp and fp in beat_fingerprints:
                groups.setdefault(fp, []).append(raw)
        except Exception:
            continue

    purged = {}
    for fp, items in groups.items():
        if len(items) > 1:
            for duplicate in items[1:]:
                r.lrem("celery", 1, duplicate)
            label = fp[1] if fp[0] == "run_service" else fp[0].split(".")[-1]
            purged[label] = len(items) - 1

    if purged:
        logger.warning("Stale beat tasks purged on startup", extra={"purged": purged})
```

## Behaviour

| Queue state | Outcome |
|-------------|---------|
| 1181 `drain_listing_actions_task` | 1180 purged, 1 kept |
| 5 `daily_scryfall_data_pipeline` | 4 purged, 1 kept (idempotency guard handles the 1 that runs) |
| 119 `run_service` pipeline chain steps | untouched |
| 6 `run_service[pricing_report]` | 5 purged, 1 kept |
| Queue empty | no-op, no log |

## What Does Not Change

- Beat schedule configuration — unchanged
- Pipeline tasks and services — unchanged
- Any task not in `beat_schedule` — never touched

## Acceptance Criteria

- After a worker restart with a bloated queue, beat-sourced task duplicates are reduced to 1 copy each
- `run_service` pipeline chain steps (e.g. `path="mtg_stock.data_staging.bulk_load"`) are never purged
- A single `WARNING` log entry lists counts of what was purged
- If the queue has no duplicates, no log is emitted and startup time is unaffected
