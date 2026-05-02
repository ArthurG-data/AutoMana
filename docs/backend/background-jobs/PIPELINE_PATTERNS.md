# Pipeline Patterns

AutoMana pipelines follow a consistent pattern for step orchestration, context passing, error handling, and observability. This document covers the **run_service dispatcher** pattern, **step-level operations tracking**, and real-world examples.

---

## Table of Contents

1. [Overview](#overview)
2. [Run Service Dispatcher Pattern](#run-service-dispatcher-pattern)
3. [Step-Level Operations Tracking (track_step)](#step-level-operations-tracking-track_step)
4. [Pipeline Step Chaining](#pipeline-step-chaining)
5. [Context Passing Between Steps](#context-passing-between-steps)
6. [Error Handling in Pipelines](#error-handling-in-pipelines)
7. [Monitoring Pipeline Health](#monitoring-pipeline-health)
8. [Common Pipeline Patterns](#common-pipeline-patterns)
9. [Code Examples](#code-examples)

---

## Overview

### Pipeline Anatomy

Every AutoMana pipeline is a **Celery chain** of **run_service** dispatcher tasks:

```
Celery chain
    ├─> run_service("staging.scryfall.start_pipeline", ...)
    ├─> run_service("staging.scryfall.get_bulk_data_uri", ...)
    ├─> run_service("staging.scryfall.download_bulk_manifests", ...)
    ├─> run_service("card_catalog.card.process_large_json", ...)
    └─> run_service("ops.pipeline_services.finish_run", status="success")
```

Each **run_service** call:
1. **Looks up** a service from the ServiceRegistry by path string
2. **Validates** kwargs against the service function signature
3. **Dispatches** the service using the ServiceManager
4. **Merges** the return value (dict) back into context
5. **Passes** accumulated context to the next step

### Why This Pattern?

- **Decoupling**: Celery task (orchestration) is separate from service (business logic)
- **Reusability**: The same service can run from HTTP, CLI, TUI, or Celery
- **Testability**: Services can be tested in isolation without mocking Celery
- **Monitoring**: Each step is tracked in the ops schema automatically
- **Flexibility**: Chains can be built dynamically or conditionally

---

## Run Service Dispatcher Pattern

### The Dispatcher Task

**File:** `src/automana/worker/main.py`

The `run_service` Celery task is the **dispatcher** that executes any registered service:

```python
@app.task(name="run_service", bind=True, acks_late=True)
def run_service(self, prev=None, path: str = None, **kwargs):
    """
    Execute a service from the registry by path string.
    
    Args:
        self: Celery task instance (provides request.id)
        prev: Return value from the previous chain step (dict)
        path: Service registry path (e.g., "staging.scryfall.get_bulk_data_uri")
        **kwargs: Additional parameters passed to the service
    
    Returns:
        dict: Accumulated context (prev merged with service return value)
    """
    state = get_state()
    set_task_id(self.request.id)
    
    # Initialize runtime if this is the first task in a new worker process
    if not state.initialized:
        init_backend_runtime()
    
    # Build context: merge prior step's result with new kwargs
    context = {}
    if isinstance(prev, dict):
        context.update(prev)
    context.update(kwargs)
    
    # Look up service and filter kwargs by signature
    service_func = ServiceManager.get_service_function(path)
    sig = inspect.signature(service_func)
    allowed_keys = set(sig.parameters.keys())
    filtered_context = {k: v for k, v in context.items() if k in allowed_keys}
    
    # Execute the service
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(path, **filtered_context)
        )
        
        # Merge result back into context for next step
        if isinstance(result, dict):
            context.update(result)
        
        return context
    except Exception:
        logger.exception("run_service_failed", extra={"service_path": path})
        raise
```

### Dispatcher Design Principles

1. **Signature filtering**: Not all context keys are passed to a service; only those that match the service's signature.
   
   ```python
   # Service signature: async def step2(ingestion_run_id: int, uri: str)
   # Context has: {"ingestion_run_id": 42, "uri": "...", "old_key": "xyz"}
   # Filtered context: {"ingestion_run_id": 42, "uri": "..."}
   ```

2. **Result merging**: The service's return value (dict) is merged into context for the next step.
   
   ```python
   # Step 1 returns: {"manifest": {...}}
   # Context before step 2: {"ingestion_run_id": 42, "manifest": {...}}
   # Step 2 can access manifest in its signature
   ```

3. **Async/sync bridge**: The task runs services (async) inside an event loop (sync context).
   
   ```python
   result = state.loop.run_until_complete(
       ServiceManager.execute_service(path, **filtered_context)
   )
   ```

---

## Step-Level Operations Tracking (track_step)

### The track_step Context Manager

**File:** `src/automana/core/services/ops/pipeline_services.py`

Every pipeline step can be tracked in the `ops` schema using the `track_step` async context manager:

```python
@asynccontextmanager
async def track_step(
    ops_repository: OpsRepository | None,
    ingestion_run_id: int | None,
    step_name: str,
    error_code: str = "step_failed",
):
    """Async context manager that tracks a pipeline step.
    
    On entry:     Updates run status to 'running' + current_step
    On clean exit: Updates run status to 'success' + current_step
    On exception:  Updates run to 'failed' + error_details, then re-raises
    """
    if not ops_repository or not ingestion_run_id:
        yield  # No-op if tracking disabled (test/standalone mode)
        return
    
    # Mark step as running
    await ops_repository.update_run(
        ingestion_run_id, status="running", current_step=step_name
    )
    
    try:
        yield  # Step executes here
    except Exception as e:
        # On error: fail step + fail run
        await ops_repository.update_run(
            ingestion_run_id,
            status="failed",
            current_step=step_name,
            error_code=error_code,
            error_details={"message": str(e)},
        )
        await ops_repository.fail_run(
            ingestion_run_id,
            error_code=error_code,
            error_details={"message": str(e), "step": step_name},
        )
        raise  # Re-raise to stop the chain
    else:
        # On success: mark step as success
        await ops_repository.update_run(
            ingestion_run_id, status="success", current_step=step_name
        )
```

### Wiring track_step into a Service

Services that use `track_step` **must**:

1. Take `ops_repository` and `ingestion_run_id` as dependencies
2. Wrap their business logic in `async with track_step(...)`
3. **Never** call `ops_repository.update_run()` or `fail_run()` directly (that's `track_step`'s job)

**Example:**

```python
from automana.core.services.ops.pipeline_services import track_step

@ServiceRegistry.register(
    "card_catalog.card.process_large_json",
    db_repositories=["card_catalog", "ops"],
)
async def process_large_json(
    card_catalog_repository: CardCatalogRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int | None = None,
    file_path: str = None,
) -> dict:
    """Process large card JSON file and load into the DB."""
    async with track_step(
        ops_repository,
        ingestion_run_id,
        step_name="card_catalog.card.process_large_json"
    ):
        # Business logic here
        count = await card_catalog_repository.load_from_file(file_path)
        return {"cards_loaded": count}
```

### Ops Schema Structure

The `ops` schema tracks runs and steps:

```sql
-- One row per pipeline execution
ops.ingestion_runs (
    id INT PRIMARY KEY,
    pipeline_name VARCHAR,
    source_name VARCHAR,
    run_key VARCHAR,           -- e.g., "scryfall_daily:2026-03-29"
    status VARCHAR,            -- "running", "success", "failed", "partial"
    current_step VARCHAR,      -- Name of step currently running
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    celery_task_id VARCHAR,    -- For linking to task logs
    error_code VARCHAR,        -- e.g., "step_failed", "api_error"
    error_details JSONB        -- {"message": "..."}
);

-- One row per named step within a run
ops.ingestion_run_steps (
    id INT PRIMARY KEY,
    ingestion_run_id INT,
    step_name VARCHAR,
    status VARCHAR,            -- "running", "success", "failed"
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    error_details JSONB
);

-- Custom metrics per run
ops.ingestion_run_metrics (
    id INT PRIMARY KEY,
    ingestion_run_id INT,
    key VARCHAR,               -- e.g., "cards_loaded", "files_rejected"
    value NUMERIC
);
```

### CLAUDE.md Rule

**Rule:** *Pipeline services must use `async with track_step(ops_repository, ingestion_run_id, "step_name")` for step-level ops tracking. Never call `ops_repository.update_run(status="running"/"success"/"failed")` directly inside a service function — `track_step` handles the None guard, the running/success/failed lifecycle, and the `error_details` key format (`"message"`).*

Why?
- `track_step` ensures the running → success/failed transition is atomic
- It handles the case where `ops_repository` or `ingestion_run_id` is `None` (standalone tests)
- It properly formats error details so all errors have a consistent shape
- Direct calls would bypass these guarantees and risk leaving a run stuck in "running" state

---

## Pipeline Step Chaining

### Celery chain() Semantics

A Celery chain executes tasks **sequentially**, passing each task's return value as the first argument to the next:

```python
from celery import chain

pipeline = chain(
    run_service.s("step1", param_a=1),
    run_service.s("step2"),           # Receives step1's result as `prev`
    run_service.s("step3"),           # Receives step2's result as `prev`
)

# Execute the chain asynchronously
result = pipeline.apply_async()

# result is a GroupResult; you can poll it
print(result.state)  # "PENDING", "STARTED", "SUCCESS", "FAILURE"
print(result.get())  # Blocks until all tasks complete; returns final result
```

### Context Flow Through the Chain

```
run_service("step1", param_a=1)
    ├─ Returns: {"ingestion_run_id": 42}
    └─> Passed as prev to next step

run_service("step2", prev={"ingestion_run_id": 42})
    ├─ Merges prev into context
    ├─ Context: {"ingestion_run_id": 42}
    ├─ Service signature: async def step2(ingestion_run_id: int)
    ├─ Filtered kwargs: {"ingestion_run_id": 42}
    ├─ Service executes and returns: {"manifest": {...}}
    ├─ Merged context: {"ingestion_run_id": 42, "manifest": {...}}
    └─> Passed as prev to next step

run_service("step3", prev={"ingestion_run_id": 42, "manifest": {...}})
    ├─ Merges prev into context
    ├─ Context: {"ingestion_run_id": 42, "manifest": {...}}
    ├─ Service signature: async def step3(ingestion_run_id: int, manifest: dict)
    ├─ Filtered kwargs: {"ingestion_run_id": 42, "manifest": {...}}
    ├─ Service executes and returns: {"downloaded": True}
    ├─ Merged context: {"ingestion_run_id": 42, "manifest": {...}, "downloaded": True}
    └─> Final result returned to caller
```

### Step Return Value Contract

Each step **must return a dict** (or None):

```python
async def step(ingestion_run_id: int) -> dict:
    """Return a dict with new keys for downstream steps."""
    return {
        "new_key": value,  # These are merged into context
        "count": 42,
    }
```

If a step returns `None`, the chain continues but no new keys are added to context:

```python
async def step() -> None:
    """Pure side effect; no output for downstream steps."""
    await do_something()
    return None  # or just omit the return
```

---

## Context Passing Between Steps

### Example: Scryfall Pipeline

The `daily_scryfall_data_pipeline` in `src/automana/worker/tasks/pipelines.py` demonstrates the full pattern:

```python
@shared_task(name="daily_scryfall_data_pipeline", bind=True)
def daily_scryfall_data_pipeline(self):
    run_key = f"scryfall_daily:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting Scryfall daily pipeline", extra={"run_key": run_key})
    
    wf = chain(
        # Step 1: Create the run record
        run_service.s("staging.scryfall.start_pipeline",
                      pipeline_name="scryfall_daily",
                      source_name="scryfall",
                      run_key=run_key,
                      celery_task_id=self.request.id
                      ),
        # Step 2: Get the manifest URI
        run_service.s("staging.scryfall.get_bulk_data_uri"),
        
        # Step 3: Download the manifest
        run_service.s("staging.scryfall.download_bulk_manifests"),
        
        # Step 4: Check for updated URIs in the manifest
        run_service.s("staging.scryfall.update_data_uri_in_ops_repository"),
        
        # Step 5: Download sets
        run_service.s("staging.scryfall.download_sets"),
        
        # Step 6: Process sets JSON
        run_service.s("card_catalog.set.process_large_sets_json"),
        
        # Step 7: Download cards bulk data
        run_service.s("staging.scryfall.download_cards_bulk"),
        
        # Step 8: Process cards JSON
        run_service.s("card_catalog.card.process_large_json"),
        
        # Step 9: Refresh search index
        run_service.s("card_catalog.card_search.refresh"),
        
        # Step 10: Download and load migrations
        run_service.s("staging.scryfall.download_and_load_migrations"),
        
        # Step 11: Mark run as success
        run_service.s("ops.pipeline_services.finish_run", status="success"),
        
        # Step 12: Cleanup old files
        run_service.s("staging.scryfall.delete_old_scryfall_folders", keep=3),
    )
    
    return wf.apply_async().id
```

### Service Signatures (What Each Step Receives)

```python
# Step 1: start_pipeline
async def start_pipeline(
    ops_repository: OpsRepository,
    pipeline_name: str,
    source_name: str,
    run_key: str,
    celery_task_id: str | None = None
) -> dict:
    ingestion_run_id = await ops_repository.start_run(...)
    return {"ingestion_run_id": ingestion_run_id}

# Step 2: get_bulk_data_uri (receives ingestion_run_id from step 1)
async def get_bulk_data_uri(
    ops_repository: OpsRepository,
    ingestion_run_id: int
) -> dict:
    uri = await ops_repository.get_bulk_data_uri()
    return {"bulk_data_manifest_uri": uri}

# Step 3: download_bulk_manifests (receives ingestion_run_id + bulk_data_manifest_uri)
async def download_bulk_manifests(
    api_repository: ScryfallApiRepository,
    ingestion_run_id: int,
    bulk_data_manifest_uri: str
) -> dict:
    manifest = await api_repository.get(bulk_data_manifest_uri)
    return {"bulk_data_manifest": manifest}

# ... and so on
```

**Key insight:** Each step's signature declares exactly what it needs from prior steps. The `run_service` dispatcher filters context by signature, so steps only receive what they actually use.

---

## Error Handling in Pipelines

### Exception Flow

When any step raises an exception:

```
Step N fails with Exception
    │
    ├─> track_step context manager catches it
    │   └─> Updates ops.ingestion_runs: status="failed", error_details={...}
    │   └─> Updates ops.ingestion_run_steps: status="failed"
    │   └─> Re-raises the exception
    │
    └─> Celery chain stops
        ├─ All downstream steps are skipped
        └─ The final result is a failed task with the exception traceback
```

### Partial Failure Handling

If some batches succeed and some fail (e.g., during bulk insert), mark the run as "partial":

```python
async def load_batch(
    ops_repository: OpsRepository,
    ingestion_run_id: int,
    batch: list,
) -> dict:
    """Load a batch; return partial results."""
    successful = []
    failed = []
    
    for item in batch:
        try:
            await db.insert(item)
            successful.append(item)
        except Exception as e:
            failed.append({"item": item, "error": str(e)})
    
    # Log the partial result; don't raise
    logger.warning("batch_load_partial", extra={
        "successful": len(successful),
        "failed": len(failed),
        "failed_items": failed,
    })
    
    # Return the counts so downstream steps know
    return {
        "successful_count": len(successful),
        "failed_count": len(failed),
        "failed_items": failed,
    }

# Then downstream, a rollup step can decide:
async def finish_run(
    ops_repository: OpsRepository,
    ingestion_run_id: int,
    failed_count: int = 0,
) -> dict:
    status = "partial" if failed_count > 0 else "success"
    await ops_repository.finish_run(ingestion_run_id, status=status)
    return {}
```

### Retry Logic

As per CLAUDE.md, **retries happen at the service level, not the task level**:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@ServiceRegistry.register("api_call.fetch_data")
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def fetch_data(api_repository) -> dict:
    """Retried internally if flaky."""
    return await api_repository.fetch()
```

If all retries fail, the exception bubbles up and fails the entire run.

---

## Monitoring Pipeline Health

### Real-Time Status Tracking

While a pipeline runs, you can poll `ops.ingestion_runs` to see current progress:

```sql
SELECT
    id, pipeline_name, status, current_step,
    started_at, finished_at,
    error_code, error_details
FROM ops.ingestion_runs
WHERE pipeline_name = 'scryfall_daily'
ORDER BY started_at DESC
LIMIT 5;
```

### Step-by-Step Timeline

View all steps for a run:

```sql
SELECT
    step_name, status,
    started_at, finished_at,
    EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_sec,
    error_details
FROM ops.ingestion_run_steps
WHERE ingestion_run_id = 42
ORDER BY started_at;
```

### Custom Metrics

Store custom metrics per run:

```python
async def finish_run(
    ops_repository: OpsRepository,
    ingestion_run_id: int,
    cards_loaded: int = 0,
    sets_loaded: int = 0,
    migrations_loaded: int = 0,
) -> dict:
    await ops_repository.finish_run(ingestion_run_id, status="success")
    
    # Record metrics
    await ops_repository.record_metric(ingestion_run_id, "cards_loaded", cards_loaded)
    await ops_repository.record_metric(ingestion_run_id, "sets_loaded", sets_loaded)
    await ops_repository.record_metric(ingestion_run_id, "migrations_loaded", migrations_loaded)
    
    return {}
```

Query metrics:

```sql
SELECT key, value
FROM ops.ingestion_run_metrics
WHERE ingestion_run_id = 42;
```

### Health Alerts

See `docs/backend/background-jobs/MONITORING.md` for pipeline health checks and alerts.

---

## Common Pipeline Patterns

### Pattern 1: Simple Linear Chain

```python
chain(
    run_service.s("step1"),
    run_service.s("step2"),
    run_service.s("step3"),
).apply_async()
```

Used by: Scryfall, MTGJson, MTGStock pipelines.

### Pattern 2: Download + Process

Many pipelines follow a two-phase pattern:

```python
chain(
    # Phase 1: Fetch from external API
    run_service.s("api.download", url="..."),
    
    # Phase 2: Process and load into DB
    run_service.s("database.load", file_path="..."),
).apply_async()
```

### Pattern 3: Parallel Groups

For independent tasks, use `group()`:

```python
from celery import group

g = group(
    run_service.s("task1"),
    run_service.s("task2"),
    run_service.s("task3"),
)

# Execute all in parallel
result = g.apply_async()

# All results are collected
print(result.get())  # [result1, result2, result3]
```

### Pattern 4: Chain + Group Combination

Chain several steps, then parallelize, then chain again:

```python
from celery import chain, group

pipeline = chain(
    run_service.s("setup"),
    group(
        run_service.s("parallel_task1"),
        run_service.s("parallel_task2"),
    ),
    run_service.s("consolidate"),
).apply_async()
```

---

## Code Examples

### Complete Service with Tracking

```python
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops.pipeline_services import track_step
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.repositories.card_catalog.card_repository import CardRepository
import logging

logger = logging.getLogger(__name__)

@ServiceRegistry.register(
    "card_catalog.card.process_large_json",
    db_repositories=["card_catalog", "ops"],
)
async def process_large_json(
    card_catalog_repository: CardRepository,
    ops_repository: OpsRepository | None,
    ingestion_run_id: int | None = None,
    file_path: str = None,
) -> dict:
    """
    Load a large card JSON file into the card catalog.
    
    Returns:
        dict with "cards_loaded" count for downstream steps
    """
    async with track_step(
        ops_repository,
        ingestion_run_id,
        step_name="card_catalog.card.process_large_json"
    ):
        logger.info("Loading cards from file", extra={"file_path": file_path})
        
        # Call the repository to load the file
        count = await card_catalog_repository.load_from_json_file(file_path)
        
        logger.info("Cards loaded", extra={"count": count})
        
        return {"cards_loaded": count}
```

### Calling the Service from a Task

```python
from automana.worker.main import run_service
from celery import chain

# Build and execute a chain
pipeline = chain(
    run_service.s("ops.pipeline_services.start_run",
                  pipeline_name="test_pipeline",
                  source_name="test",
                  run_key="test:2026-03-29",
                  celery_task_id="xyz"),
    run_service.s("card_catalog.card.process_large_json",
                  file_path="/path/to/cards.json"),
    run_service.s("ops.pipeline_services.finish_run",
                  status="success"),
).apply_async()

print(f"Pipeline task ID: {pipeline.id}")
```

### Testing a Service in Isolation

```python
import asyncio
from automana.core.service_manager import ServiceManager
from automana.core.database import init_async_pool
from automana.core.settings import Settings

async def test():
    # Initialize the service manager (usually done in main.py)
    pool = await init_async_pool(Settings())
    await ServiceManager.initialize(pool)
    
    # Execute the service directly (no Celery needed)
    result = await ServiceManager.execute_service(
        "card_catalog.card.process_large_json",
        file_path="/path/to/test.json",
        ingestion_run_id=None,  # No ops tracking in test
    )
    
    print(result)  # {"cards_loaded": 42}

# Run the test
asyncio.run(test())
```

---

## See Also

- [`docs/backend/background-jobs/CELERY_ARCHITECTURE.md`](CELERY_ARCHITECTURE.md) — Celery task execution framework
- [`docs/backend/background-jobs/MONITORING.md`](MONITORING.md) — Observability and health checks
- [`docs/SCRYFALL_PIPELINE.md`](../../SCRYFALL_PIPELINE.md) — Detailed Scryfall pipeline walkthrough
- [`docs/MTGSTOCK_PIPELINE.md`](../../MTGSTOCK_PIPELINE.md) — MTGStock pipeline and reject handling
- [`docs/DESIGN_PATTERNS.md`](../../DESIGN_PATTERNS.md) § Chain of Responsibility — Celery chain pattern explanation
- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) — Overall system layers and request flow
