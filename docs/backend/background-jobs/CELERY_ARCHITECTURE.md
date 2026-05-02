# Celery Architecture

AutoMana uses **Celery** with **Redis** for distributed background task execution. This document covers the task execution framework, configuration, and integration with the service layer.

---

## Table of Contents

1. [Overview](#overview)
2. [Celery & Redis Setup](#celery--redis-setup)
3. [Task Organization](#task-organization)
4. [Task Execution Flow](#task-execution-flow)
5. [Retry & Exponential Backoff](#retry--exponential-backoff)
6. [Result Storage](#result-storage)
7. [Monitoring & Observability](#monitoring--observability)
8. [Scaling Considerations](#scaling-considerations)
9. [Common Patterns](#common-patterns)

---

## Overview

### What is Celery?

Celery is a distributed task queue that executes async functions asynchronously across a pool of workers. In AutoMana:

- **Broker** (message queue): Redis at `redis://redis:6379/0`
- **Result backend** (result store): Redis at `redis://redis:6379/1`
- **Worker process**: Dedicated Python process that consumes tasks and executes them
- **Beat scheduler**: Optional periodic task scheduler that enqueues tasks on a cron schedule

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      Task Sources                               │
├──────────────────┬──────────────────┬──────────────────┐────────┤
│   FastAPI HTTP   │   Celery Beat    │   CLI / TUI      │  Manual│
│   Endpoint       │   Scheduler      │   Invocation     │  Trigger
└────────┬─────────┴────────┬─────────┴──────────┬───────┘────────┘
         │                  │                    │
         v                  v                    v
    ┌─────────────────────────────────────┐
    │     Redis Broker (Task Queue)        │
    │  redis://redis:6379/0               │
    └─────┬───────────────────────────────┘
          │
          │  (consume)
          v
┌──────────────────────────────────────────┐
│   Celery Worker (Process)                │
│                                          │
│  @worker_process_init:                   │
│    • init_backend_runtime()              │
│    • initialize ServiceManager           │
│    • setup logging                       │
│                                          │
│  Execution loop:                         │
│    1. Poll Redis for new tasks           │
│    2. Deserialize task + args            │
│    3. Set task_id in logging context     │
│    4. Execute task function              │
│    5. Capture result/exception           │
│    6. Publish to result backend          │
│    7. ACK the broker message             │
└──────────────────────────────────────────┘
         │
         └──> Redis Result Backend
              redis://redis:6379/1
              (store return value)
```

---

## Celery & Redis Setup

### Configuration File

Configuration lives in [`src/automana/worker/celeryconfig.py`](../../src/automana/worker/celeryconfig.py):

```python
# Broker & result backend URIs
broker_url = os.getenv("BROKER_URL", f"redis://{_default_redis_host}:6379/0")
result_backend = os.getenv("RESULT_BACKEND", f"redis://{_default_redis_host}:6379/1")

# Task module imports (tasks that can be executed)
imports = {
    "automana.worker.tasks.pipelines",
    "automana.worker.tasks.analytics",
}

# Worker settings
worker_prefetch_multiplier = 1      # Fetch only 1 task at a time (careful workers)
task_always_eager = False            # Don't execute tasks synchronously (real queue)
task_store_eager_result = True       # Store results even for eager execution

# Timezone (Australia/Sydney) — important for Beat schedule interpretation
timezone = os.getenv("CELERY_TIMEZONE", "Australia/Sydney")

# Beat schedule (periodic tasks)
beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "automana.worker.tasks.pipelines.daily_scryfall_data_pipeline",
        "schedule": crontab(hour=2, minute=0),  # 02:00 AEST
    },
    # ... more tasks
}
```

### Runtime Initialization

The Celery app is created in [`src/automana/worker/main.py`](../../src/automana/worker/main.py):

```python
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

app = Celery('etl')
app.config_from_object("automana.worker.celeryconfig")

@worker_process_init.connect
def _init(**_):
    configure_logging()
    init_backend_runtime()      # Initialize ServiceManager + DB pool

@worker_process_shutdown.connect
def _shutdown(**_):
    shutdown_backend_runtime()  # Close DB pool
```

**Key points:**
- `worker_process_init` runs **once per worker process**, not per task
- This is where the `ServiceManager` singleton is initialized with the DB pool
- The initialization is **shared by all tasks executed by that worker**

### Docker Compose Setup

In `deploy/docker-compose.dev.yml`:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery-worker:
    build: .
    command: >
      celery -A automana.worker.main:app worker
        --loglevel=info
        --prefetch-multiplier=1
        --pool=prefork
        --concurrency=2
    environment:
      BROKER_URL: redis://redis:6379/0
      RESULT_BACKEND: redis://redis:6379/1
      LOG_JSON: "1"
    depends_on:
      - redis
      - postgres

  celery-beat:
    build: .
    command: >
      celery -A automana.worker.main:app beat
        --loglevel=info
        --scheduler=redbeat.RedBeatScheduler
    environment:
      BROKER_URL: redis://redis:6379/0
      RESULT_BACKEND: redis://redis:6379/1
    depends_on:
      - redis
```

---

## Task Organization

### Task Naming Convention

All tasks are defined in `src/automana/worker/tasks/` with explicit task names:

```python
from celery import shared_task

@shared_task(name="daily_scryfall_data_pipeline", bind=True)
def daily_scryfall_data_pipeline(self):
    """Celery task (the entry point)."""
    # Task code here
```

The `name=` parameter is the **queue key** — if you omit it, Celery defaults to `module.function`, which is fragile.

### Task Modules

| Module | Responsibility |
|--------|-----------------|
| `automana.worker.tasks.pipelines` | Daily/hourly ETL pipelines (Scryfall, MTGJson, MTGStock) |
| `automana.worker.tasks.analytics` | Analytics aggregation and reporting |
| `automana.worker.tasks.app_authentification` | OAuth / external API authentication flows |
| `automana.worker.tasks.ebay` | eBay integration (future: polling, listing sync) |

Each module exports top-level `@shared_task` functions that Celery can discover at startup.

### Service Dispatch Pattern

The core pattern for all pipeline tasks is:

```python
@shared_task(name="daily_scryfall_data_pipeline", bind=True)
def daily_scryfall_data_pipeline(self):
    """Celery task entry point."""
    run_key = f"scryfall_daily:{date.today().isoformat()}"
    logger.info("Starting Scryfall daily pipeline", extra={"run_key": run_key})
    
    # Define a chain of service calls (via run_service dispatcher)
    wf = chain(
        run_service.s("staging.scryfall.start_pipeline", run_key=run_key, ...),
        run_service.s("staging.scryfall.get_bulk_data_uri"),
        run_service.s("staging.scryfall.download_bulk_manifests"),
        # ... more steps
    )
    
    # Execute the chain asynchronously
    return wf.apply_async().id
```

The task itself is **thin** — it just orchestrates the chain. All business logic lives in **services** (see `docs/backend/background-jobs/PIPELINE_PATTERNS.md`).

---

## Task Execution Flow

### The `run_service` Dispatcher Task

The workhorse task is `run_service` — a Celery task that dispatches any service from the `ServiceRegistry` by path:

**File:** `src/automana/worker/main.py`

```python
@app.task(
    name="run_service",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 0},  # Retries disabled; handled at run_service level
    retry_backoff=True,                # But if retried, use exponential backoff
    acks_late=True                     # Only ACK after task completes successfully
)
def run_service(self, prev=None, path: str = None, **kwargs):
    """Dispatch a service function from the registry by path string."""
    state = get_state()
    set_task_id(self.request.id)
    
    if path:
        set_service_path(path)
    
    # Initialize runtime if not already done
    if not state.initialized:
        init_backend_runtime()
    
    # Chain context: merge prev result (dict) into kwargs for next step
    context = {}
    if isinstance(prev, dict):
        context.update(prev)
    context.update(kwargs)
    
    # Get service function signature and filter kwargs
    service_func = ServiceManager.get_service_function(path)
    sig = inspect.signature(service_func)
    allowed_keys = set(sig.parameters.keys())
    filtered_context = {k: v for k, v in context.items() if k in allowed_keys}
    
    logger.debug("run_service_start", extra={
        "service_path": path,
        "kwargs_keys": list(filtered_context.keys())
    })
    
    try:
        # Run the async service in the event loop
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(path, **filtered_context)
        )
        
        # 🔑 CRITICAL: Merge result back into context for next chain step
        if isinstance(result, dict):
            context.update(result)
        
        return context  # Passed as `prev` to next chain step
    
    except Exception:
        logger.exception("run_service_failed", extra={"service_path": path})
        raise
    finally:
        set_service_path(None)
        set_request_id(None)
        set_task_id(None)
```

### Execution Sequence

When a pipeline task executes:

```
1. Celery worker picks task from Redis queue
   └─> Deserializes args, keyword args

2. @worker_process_init fires (first time only per worker process)
   └─> initialize ServiceManager, DB pool, logging

3. Task function executes (e.g., daily_scryfall_data_pipeline)
   └─> Builds a Celery chain of run_service calls
   └─> Calls chain.apply_async() to enqueue the chain

4. Each run_service task executes in sequence
   ├─> Deserializes (service path, prior step context)
   ├─> Looks up service in ServiceRegistry
   ├─> Validates kwargs against service signature
   ├─> Executes: ServiceManager.execute_service(path, **filtered_context)
   ├─> Merges result (dict) back into context for next step
   └─> Returns context to next run_service task

5. Final step returns; Celery publishes result to Redis result backend

6. Task is ACK'd to the broker (removed from queue)
```

### Chain Context Passing

Celery's `chain()` automatically passes the **return value** of one task as the first argument to the next:

```python
chain(
    run_service.s("step1", param_a=1),
    run_service.s("step2"),           # Receives step1's result as `prev`
    run_service.s("step3"),           # Receives step2's result as `prev`
)
```

The `run_service` dispatcher extracts prior context from `prev` and merges it with new kwargs so downstream steps can access all accumulated data:

```
Step 1 returns: {"ingestion_run_id": 42, "uri": "https://..."}
    ↓
Step 2 receives: prev={"ingestion_run_id": 42, "uri": "https://..."}
                 path="staging.scryfall.get_bulk_data_uri"
    ↓
Step 2 service gets: ingestion_run_id=42, uri="https://..."
                     (signature-filtered from context)
    ↓
Step 2 returns: {"bulk_data_manifest": {...}}
    ↓
Step 3 receives: prev={"ingestion_run_id": 42, "uri": "https://...", "bulk_data_manifest": {...}}
                 path="staging.scryfall.download_bulk_manifests"
    ↓
Step 3 service gets: ingestion_run_id=42, uri="https://...", bulk_data_manifest={...}
```

---

## Retry & Exponential Backoff

### Task-level Configuration

The `run_service` task is configured with:

```python
@app.task(
    name="run_service",
    bind=True,
    autoretry_for=(Exception,),      # Auto-retry on ANY exception
    retry_kwargs={"max_retries": 0}, # But NO retries (handled at run_service level)
    retry_backoff=True,              # If retried, use exponential backoff
    acks_late=True                   # ACK only after successful completion
)
```

### Design: Why Retries are Disabled at Task Level

**CLAUDE.md rule:** *Pipeline tasks must not use `autoretry_for` — retry logic is handled at the `run_service` level.*

This is a deliberate design choice:

- Celery's task-level `autoretry_for` would cause the entire chain to be retried from the start.
- Instead, retries are implemented **inside the service layer** where granular decisions can be made.
- Example: if step 5 of a 10-step pipeline fails with a transient error, retrying the service call directly is cheaper than restarting from step 1.

### Service-level Retry

Services that need retry logic implement it internally:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@ServiceRegistry.register("my_service.fetch_data")
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def fetch_data(api_repository: SomeApiRepository) -> dict:
    # External API call that might be flaky
    return await api_repository.get_data()
```

When retried at the service level:
1. The retry happens **within the running task** (no round-trip to the broker).
2. The event loop continues; no new task is enqueued.
3. If it succeeds, the chain continues normally.
4. If it exhausts retries, the exception bubbles up to the task, which fails the entire run.

---

## Result Storage

### Result Backend (Redis)

Results are stored in Redis at `redis://redis:6379/1` by default.

**Result TTL:** Controlled by `result_expires` in celeryconfig (default: 1 hour in dev, 24 hours in prod).

```python
result_expires = int(os.getenv("CELERY_RESULT_EXPIRES", 86400))  # seconds
```

### Accessing Results

From the FastAPI app or CLI:

```python
from automana.worker.main import app as celery_app

task_id = "abc123..."
result = celery_app.AsyncResult(task_id)

# Check status
result.state  # "PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY"

# Get return value (blocks until ready)
try:
    data = result.get(timeout=30)  # dict of accumulated context
except Exception as e:
    print(f"Task failed: {e}")
```

### Serialization Format

Results are serialized as **JSON** (set in celeryconfig). The context dict returned from `run_service` is JSON-serializable:

```python
{
    "ingestion_run_id": 42,
    "source_name": "scryfall",
    "bulk_data_manifest": {...},
    "error": null
}
```

---

## Monitoring & Observability

### Logging from Tasks

All tasks and services use **structured JSON logging**. The Celery worker initializes logging in `@worker_process_init`:

```python
@worker_process_init.connect
def _init(**_):
    configure_logging()  # Sets up JSON formatter + context filter
    init_backend_runtime()
```

Every log line includes:

| Field | Source |
|-------|--------|
| `ts` | UTC timestamp |
| `level` | Log level |
| `logger` | Module name |
| `msg` | Log message |
| `task_id` | Celery task ID (set by `set_task_id()`) |
| `service_path` | Active service being dispatched |
| Custom fields | Passed via `extra={}` |

**Example:**

```python
logger.info("Pipeline started", extra={
    "run_key": "scryfall_daily:2026-03-29",
    "pipeline_name": "scryfall_daily",
})
```

Produces:

```json
{
  "ts": "2026-03-29T02:00:00Z",
  "level": "INFO",
  "logger": "automana.worker.tasks.pipelines",
  "msg": "Pipeline started",
  "task_id": "abc123def456",
  "service_path": "staging.scryfall.start_pipeline",
  "run_key": "scryfall_daily:2026-03-29",
  "pipeline_name": "scryfall_daily"
}
```

### Ops Tracking

Pipeline execution is tracked in the `ops` schema:

```
ops.ingestion_runs          # One row per pipeline execution
ops.ingestion_run_steps     # One row per named step
ops.ingestion_run_metrics   # Custom metrics per run
```

Each `run_service` call that uses `track_step()` updates these tables automatically (see `docs/backend/background-jobs/PIPELINE_PATTERNS.md` for details).

### Flower — Web UI for Celery

Flower is an optional monitoring dashboard for Celery:

```bash
pip install flower
celery -A automana.worker.main:app flower --port=5555
```

Then visit `http://localhost:5555` to see:
- Active tasks
- Task history
- Worker pool status
- Queue depth
- Task success/failure rates

---

## Scaling Considerations

### Concurrency Model

The dev docker-compose uses:

```yaml
command: >
  celery -A automana.worker.main:app worker
    --loglevel=info
    --prefetch-multiplier=1
    --pool=prefork
    --concurrency=2
```

**Key settings:**

| Setting | Value | Meaning |
|---------|-------|---------|
| `pool` | `prefork` | Fork child processes; each gets a full Python interpreter + DB pool |
| `concurrency` | 2 | 2 worker processes (adjust based on CPU cores) |
| `prefetch-multiplier` | 1 | Fetch only 1 task per worker at a time (prevents one slow task hogging the queue) |

**For production**, use a larger `concurrency` value and monitor memory (each worker has its own DB pool).

### Database Connection Pool

Each worker process initializes its own asyncpg pool in `@worker_process_init`:

```python
@worker_process_init.connect
def _init(**_):
    init_backend_runtime()  # Creates asyncpg pool with default 20 connections
```

With 2 workers, you get 2 × 20 = 40 connections to Postgres. The pool is **shared by all tasks executing in that worker process**.

### Memory and CPU

- **Memory**: Each worker process is a full Python interpreter. With 4 workers, expect 4 × ~200 MB = ~800 MB base.
- **CPU**: Pipeline tasks are I/O-bound (API calls, DB queries), so `concurrency` can exceed CPU cores.
- **Prefetch**: `prefetch-multiplier=1` ensures tasks are distributed fairly — a slow task won't block other workers.

### Separate Queue for Long-Running Tasks

For future high-concurrency scenarios, separate queues can route tasks:

```python
@app.task(name="heavy_task", queue="heavy")
def heavy_task():
    # CPU-intensive work
    pass

@app.task(name="light_task", queue="light")
def light_task():
    # I/O-bound work
    pass
```

Then start workers for each queue:

```bash
# Worker for light I/O tasks (high concurrency)
celery -A automana.worker.main:app worker -Q light --concurrency=8

# Worker for heavy CPU tasks (low concurrency)
celery -A automana.worker.main:app worker -Q heavy --concurrency=2
```

---

## Common Patterns

### 1. Simple Task

```python
from celery import shared_task

@shared_task(name="simple_task")
def simple_task(user_id: int):
    # Do something
    return {"result": "done"}

# Enqueue:
simple_task.delay(user_id=123)
```

### 2. Scheduled Task (Beat)

Add to `celeryconfig.py`:

```python
beat_schedule = {
    "my-hourly-task": {
        "task": "automana.worker.tasks.mymodule.my_task",
        "schedule": crontab(minute=0),  # Every hour at :00
    },
}
```

### 3. Chain (Sequential Tasks)

```python
from celery import chain

chain(
    run_service.s("step1"),
    run_service.s("step2"),
    run_service.s("step3"),
).apply_async()
```

### 4. Group (Parallel Tasks)

```python
from celery import group

g = group(
    run_service.s("task1"),
    run_service.s("task2"),
    run_service.s("task3"),
)
result = g.apply_async()

# Wait for all to complete
print(result.get())  # [result1, result2, result3]
```

### 5. Monitoring Task Status

```python
from automana.worker.main import app

task_id = "..."
ar = app.AsyncResult(task_id)

print(ar.state)     # "PENDING", "STARTED", "SUCCESS", "FAILURE"
print(ar.ready())   # True if completed
print(ar.successful())  # True if succeeded

if ar.state == "SUCCESS":
    print(ar.result)
elif ar.state == "FAILURE":
    print(ar.traceback)  # Exception traceback
```

---

## See Also

- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) — Overall system layers and request flow
- [`docs/backend/background-jobs/PIPELINE_PATTERNS.md`](PIPELINE_PATTERNS.md) — ETL pipeline patterns and `track_step`
- [`docs/backend/background-jobs/MONITORING.md`](MONITORING.md) — Observability for background jobs
- [`docs/SCRYFALL_PIPELINE.md`](../../SCRYFALL_PIPELINE.md) — Real pipeline example
- [`docs/MTGSTOCK_PIPELINE.md`](../../MTGSTOCK_PIPELINE.md) — Real pipeline example
- [Celery Documentation](https://docs.celeryproject.io/)
