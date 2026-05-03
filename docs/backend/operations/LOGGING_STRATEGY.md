# Logging Strategy

AutoMana uses structured, context-aware logging built on Python's standard `logging` module. This design ensures that all logs are machine-readable, traceable across async operations, and queryable by request or task ID.

**Related files:**
- `src/automana/core/logging_context.py` — Context variable management
- `src/automana/core/logging_config.py` — Root logger setup, formatters, filters
- `docs/LOGGING.md` — Quick reference

---

## Logging Setup and Configuration

### One-time initialization

Call `configure_logging()` once per process at startup. The function is idempotent (guarded by a `_automana_configured` flag), so it is safe to call multiple times.

**FastAPI entrypoint** (`src/automana/api/main.py`):

```python
from automana.core.logging_config import configure_logging
configure_logging()
logger = logging.getLogger(__name__)
logger.info("Application startup initiated")
```

**Celery worker entrypoint** (e.g., `src/automana/worker/__main__.py`):

```python
from automana.core.logging_config import configure_logging
configure_logging()
logger = logging.getLogger(__name__)
```

All module-level loggers created with `logging.getLogger(__name__)` automatically inherit the root handler and context filter — no per-module setup is needed.

### Configuration

All configuration is set via environment variables:

| Env var | Default | Purpose |
|---------|---------|---------|
| `LOG_LEVEL` | `INFO` | Root logger level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_JSON` | `1` | Set to `0` for human-readable output; `1` for JSON (production default) |
| `SERVICE_NAME` | `unknown` | Service identifier in logs (e.g., `backend`, `celery-worker`) |
| `APP_ENV` | `dev` | Environment identifier in logs (e.g., `dev`, `staging`, `prod`) |

Example: enable debug logging for development

```bash
LOG_LEVEL=DEBUG LOG_JSON=0 docker compose -f deploy/docker-compose.dev.yml up
```

---

## Static Message + Extra Fields Pattern

**The golden rule:** Keep the message string static; put all dynamic data into `extra={...}`.

This design ensures:
- Logs can be grouped by identical message strings (e.g., "Pipeline step completed" across 1000 requests)
- Structured fields are discrete JSON keys, not embedded in the text
- Aggregation queries can reliably filter by message and inspect fields

### Correct (static message, structured fields)

```python
logger.info("Pipeline step completed", extra={
    "step_name": "scryfall_download",
    "cards_downloaded": 12500,
    "duration_seconds": 45.23,
    "status": "success"
})
```

JSON output:
```json
{
  "ts": "2026-05-02T14:30:45.123Z",
  "level": "INFO",
  "logger": "automana.worker.tasks.pipelines",
  "msg": "Pipeline step completed",
  "service": "celery-worker",
  "env": "prod",
  "task_id": "abc-123-def",
  "step_name": "scryfall_download",
  "cards_downloaded": 12500,
  "duration_seconds": 45.23,
  "status": "success"
}
```

### Incorrect (dynamic message, loses structure)

```python
# BAD: message is dynamic, field extraction is manual
logger.info(f"Pipeline step scryfall_download completed: 12500 cards in 45.23s")

# BAD: uses % formatting
logger.info("Pipeline step %s completed with status %s", step_name, status)
```

### Exception logging

Always use `logger.exception()` (or `logger.error(..., exc_info=True)`) to capture the full traceback in JSON:

```python
try:
    await download_from_scryfall()
except Exception as e:
    logger.error("Download failed after retries", extra={
        "attempt": 5,
        "error_type": type(e).__name__,
        "error_message": str(e)
    })
    raise
```

JSON output includes `"exc_info": "<traceback>"` automatically.

---

## Log Levels and When to Use Each

### DEBUG

Use for detailed troubleshooting information that is verbose enough to slow down normal operation.

```python
logger.debug("Attempting to fetch from URL", extra={"url": url, "timeout_seconds": 30})
logger.debug("Parsing response", extra={"response_size_bytes": len(response), "encoding": "utf-8"})
```

Enable during development or when debugging a reported issue:

```bash
LOG_LEVEL=DEBUG docker compose up
```

### INFO

Use for significant events: process startup, pipeline steps, important state changes.

```python
logger.info("Pipeline started", extra={"pipeline_name": "scryfall_etl", "run_id": run_id})
logger.info("Batch processed successfully", extra={"batch_id": batch_id, "records": 500})
logger.info("Database migration applied", extra={"migration": "20_add_pricing_tables"})
```

### WARNING

Use when something unexpected happened but the system recovered or will retry.

```python
logger.warning("API rate limit approaching", extra={"current_rate": 95, "limit": 100})
logger.warning("Retry after transient error", extra={"attempt": 3, "next_attempt_in_seconds": 5})
logger.warning("Missing optional field in response", extra={"field": "foil_price", "url": url})
```

### ERROR

Use when an operation failed but the system is still running.

```python
logger.error("Batch failed after max retries", extra={
    "batch_id": batch_id,
    "max_retries": 5,
    "error": str(e)
})
```

### CRITICAL

Use when the process cannot continue and must exit or manually restart.

```python
logger.critical("Database connection pool exhausted", extra={"pool_size": 10})
logger.critical("Redis unreachable; caching disabled", extra={"redis_url": "..."})
```

---

## Context Variables

Context is stored in `contextvars.ContextVar` — each asyncio coroutine (HTTP request or Celery task) gets its own isolated copy. This ensures concurrent requests never bleed context into each other.

**Defined in** `src/automana/core/logging_context.py`:

### request_id

Set by FastAPI middleware on every HTTP request. Links all log lines for a single request.

**Setter:** `set_request_id(request_id)`  
**Getter:** `get_request_id()`  
**Set by:** HTTP request ID middleware in `src/automana/api/main.py`

```python
# Middleware generates or extracts request ID
request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
set_request_id(request_id)
response.headers["X-Request-ID"] = request_id
```

**Log query:** Find all logs for a single HTTP request

```bash
# Assuming Loki or similar aggregation backend
curl -s 'http://logs:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={request_id="abc-123"}' \
  | jq '.data.result[].values'
```

### task_id

Set by the Celery worker before executing a task. Links all log lines for a single background job.

**Setter:** `set_task_id(task_id)`  
**Getter:** `get_task_id()`  
**Set by:** Celery worker entrypoint (receives `task.request.id` from Celery)

```python
# In the celery worker entrypoint
set_task_id(task.request.id)  # Celery's unique task ID
logger.info("Task started", extra={"task_name": task.name})
```

**Log query:** Find all logs for a single background task

```bash
curl -s 'http://logs:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={task_id="acdf-4321"}' \
  | jq '.data.result[].values'
```

### service_path

Set by FastAPI middleware or the ServiceManager dispatcher. Identifies which service registry entry is executing.

**Setter:** `set_service_path(service_path)`  
**Getter:** `get_service_path()`  
**Set by:** `service_path_middleware` in `src/automana/api/main.py`

Format: `http.{method}.{route_name}` for HTTP, or `pipeline.{pipeline_name}.{step_name}` for Celery tasks.

Examples:

```
http.get.get_user_profile
http.post.create_card
pipeline.scryfall_etl.download_cards
```

**Log query:** Find all logs for a specific service

```bash
curl -s 'http://logs:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={service_path="http.post.create_card"}' \
  | jq '.data.result[].values'
```

---

## JSON Output Format

All logs are emitted as JSON objects (one per line) when `LOG_JSON=1` (production default).

### Fixed fields (always present)

| Field | Source | Example |
|-------|--------|---------|
| `ts` | `datetime.now(timezone.utc).isoformat()` | `"2026-05-02T14:30:45.123456Z"` |
| `level` | `LogRecord.levelname` | `"INFO"`, `"ERROR"`, etc. |
| `logger` | `LogRecord.name` (usually `__name__`) | `"automana.worker.tasks.scryfall"` |
| `msg` | Formatted message string | `"Pipeline step completed"` |
| `service` | `SERVICE_NAME` env var | `"backend"`, `"celery-worker"` |
| `env` | `APP_ENV` env var | `"dev"`, `"staging"`, `"prod"` |
| `request_id` | Active HTTP request ID or `None` | `"550e8400-e29b-41d4-a716-446655440000"` |
| `task_id` | Active Celery task ID or `None` | `"abc-123-def-456"` |
| `service_path` | Active service registry path or `None` | `"http.post.create_card"` |

### Dynamic fields (from `extra={}`)

Any keys passed via `extra={...}` are merged into the JSON payload, as long as they don't collide with [Python's reserved `LogRecord` attributes](https://docs.python.org/3/library/logging.html#logrecord-attributes).

**Reserved attributes (avoid as keys):**

```
name, msg, args, levelname, levelno, pathname, filename, module,
exc_info, exc_text, stack_info, lineno, funcName, created, msecs,
relativeCreated, thread, threadName, processName, process, message, asctime
```

Use unambiguous names instead:

```python
# Good: unambiguous
logger.info("Update completed", extra={"file": filename, "line": lineno, "module_name": module})

# Bad: uses reserved names (these will be silently ignored or cause JSON conflicts)
logger.info("Update completed", extra={"filename": f, "lineno": 42, "module": m})
```

### Example full log entry

```json
{
  "ts": "2026-05-02T14:30:45.123456Z",
  "level": "INFO",
  "logger": "automana.worker.tasks.scryfall",
  "msg": "Batch processed successfully",
  "service": "celery-worker",
  "env": "prod",
  "request_id": null,
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "service_path": "pipeline.scryfall_etl.process_bulk_data",
  "batch_id": 42,
  "records_processed": 15000,
  "duration_ms": 2345,
  "status": "success"
}
```

---

## Log Aggregation and Querying

### Local development (stdout)

During development, logs are printed to stdout in the container:

```bash
docker compose -f deploy/docker-compose.dev.yml logs -f backend
```

Filter by JSON fields (if using `jq`):

```bash
docker compose logs -f backend | jq 'select(.level == "ERROR")'
docker compose logs -f backend | jq 'select(.service_path | contains("create_card"))'
```

### Production aggregation

In production, configure your observability backend (e.g., Loki, ELK, Grafana) to ingest `stdout` from all containers. The structured JSON format ensures automatic field extraction.

**Loki scrape config** (example):

```yaml
scrape_configs:
  - job_name: automana-backend
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
    relabel_configs:
      - source_labels: [__meta_docker_container_name]
        target_label: container
      - source_labels: [__meta_docker_container_label_app]
        target_label: app
    json_config:
      time_key: ts
      time_format: "2006-01-02T15:04:05.000000Z07:00"
```

**Grafana log queries** (LogQL):

```promql
# All ERROR logs
{app="automana"} | json | level="ERROR"

# Errors in a specific service
{app="automana"} | json | service_path="http.post.create_card" | level="ERROR"

# All logs for a specific HTTP request
{app="automana"} | json | request_id="550e8400-e29b-41d4-a716-446655440000"

# Pipeline step duration analysis
{app="automana"} | json | service_path=~"pipeline.scryfall_etl.*" | avg(duration_ms) by (service_path)
```

### Local testing and inspection

Install `jq` for JSON log filtering:

```bash
# All logs at ERROR or above
docker compose logs backend | jq 'select(.level == "ERROR" or .level == "CRITICAL")'

# Group by service_path
docker compose logs backend | jq '.service_path' | sort | uniq -c

# Calculate average duration_ms by step
docker compose logs backend | jq 'select(.duration_ms != null) | {service_path, duration_ms}' \
  | jq -s 'group_by(.service_path) | map({step: .[0].service_path, avg_ms: (map(.duration_ms) | add / length)})'
```

---

## Performance Considerations

### Log volume and I/O

Logging is asynchronous (writes to `stdout`, which is buffered). However, high-frequency logging (e.g., inside tight loops) can still degrade performance.

**Guidelines:**

- Use `DEBUG` level for per-item logging (inside loops). Keep production at `INFO`.
- Avoid logging the same static message thousands of times per second. Instead, log once with aggregated counts.

**Good:**

```python
successful_count = 0
failed_count = 0
for card_id in card_ids:
    try:
        await process_card(card_id)
        successful_count += 1
    except Exception:
        failed_count += 1

logger.info("Batch processing complete", extra={
    "total": len(card_ids),
    "successful": successful_count,
    "failed": failed_count
})
```

**Bad (thousands of logs):**

```python
for card_id in card_ids:
    logger.debug(f"Processing card {card_id}")  # 10k logs
    try:
        await process_card(card_id)
        logger.debug(f"Processed card {card_id}")  # 10k logs
    except Exception as e:
        logger.debug(f"Failed to process card {card_id}: {e}")  # potentially 10k logs
```

### Serialization overhead

The JSON formatter calls `json.dumps()` on every log record. For most logs (object keys, strings, numbers), this is fast (<1ms). However, large nested structures or circular references should be avoided.

**Good:**

```python
logger.info("Card prices updated", extra={
    "card_id": card_id,
    "old_price": 10.50,
    "new_price": 12.75
})
```

**Bad (large object serialization):**

```python
# Don't pass the entire Card object
logger.info("Card prices updated", extra={"card": card_obj})
```

### Context variable overhead

Context variables are O(1) — reading them is a simple dict lookup and carries negligible overhead.

---

## Code Examples

### HTTP request logging

```python
import logging
from fastapi import FastAPI
from automana.core.logging_config import configure_logging
from automana.core.logging_context import set_request_id, get_request_id

configure_logging()
logger = logging.getLogger(__name__)
app = FastAPI()

@app.get("/cards/{card_id}")
async def get_card(card_id: int):
    request_id = get_request_id()  # Already set by middleware
    logger.info("Fetching card", extra={"card_id": card_id})
    
    try:
        card = await fetch_from_db(card_id)
        logger.info("Card fetched successfully", extra={
            "card_id": card_id,
            "set_code": card.set_code
        })
        return card
    except CardNotFoundError as e:
        logger.warning("Card not found", extra={"card_id": card_id})
        raise HTTPException(status_code=404, detail="Card not found")
    except Exception as e:
        logger.error("Unexpected error", extra={
            "card_id": card_id,
            "error_type": type(e).__name__
        })
        raise
```

### Celery task logging

```python
import logging
from celery import shared_task
from automana.core.logging_context import get_task_id

logger = logging.getLogger(__name__)

@shared_task
def process_card_batch(batch_id: int):
    # task_id is set by worker entrypoint
    batch_size = 1000
    processed = 0
    failed = 0
    
    logger.info("Starting batch processing", extra={"batch_id": batch_id})
    
    try:
        cards = fetch_batch_cards(batch_id)
        for card in cards:
            try:
                update_card_price(card)
                processed += 1
            except Exception as e:
                logger.warning("Failed to update card", extra={
                    "card_id": card.id,
                    "error": str(e)
                })
                failed += 1
        
        logger.info("Batch processing complete", extra={
            "batch_id": batch_id,
            "processed": processed,
            "failed": failed,
            "total_time_seconds": time.time() - start
        })
    except Exception as e:
        logger.error("Batch processing failed", extra={
            "batch_id": batch_id,
            "error_type": type(e).__name__
        })
        raise
```

### Service layer logging

```python
import logging
from automana.core.logging_context import get_service_path

logger = logging.getLogger(__name__)

async def create_user_profile(user_id: int, profile_data: dict) -> User:
    service_path = get_service_path()  # "http.post.create_user_profile"
    logger.info("Creating user profile", extra={
        "user_id": user_id,
        "fields": len(profile_data)
    })
    
    try:
        user = await users_repository.create(user_id, **profile_data)
        logger.info("User profile created", extra={
            "user_id": user_id,
            "profile_id": user.profile_id
        })
        return user
    except ValueError as e:
        logger.warning("Validation error", extra={
            "user_id": user_id,
            "error": str(e)
        })
        raise
```

---

## Summary

AutoMana's logging design emphasizes:

1. **Structure:** JSON output with fixed and dynamic fields
2. **Traceability:** `request_id`, `task_id`, `service_path` link all logs for a single operation
3. **Clarity:** Static message strings with structured fields (never interpolate values into the message)
4. **Queryability:** Logs can be aggregated, filtered, and analyzed by infrastructure tools
5. **Performance:** Asynchronous I/O, minimal serialization overhead, context variables with negligible cost

Always prefer logging at the service layer and with extra fields rather than inside tight loops.
