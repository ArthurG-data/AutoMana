# Logging

AutoMana uses structured, context-aware logging built on Python's standard `logging` module.
Configuration lives in two files:

| File | Responsibility |
|---|---|
| [`src/automana/core/logging_context.py`](../src/automana/core/logging_context.py) | Per-coroutine context variables (`request_id`, `task_id`, `service_path`) |
| [`src/automana/core/logging_config.py`](../src/automana/core/logging_config.py) | Root logger setup, JSON formatter, context filter |

---

## Setup

Call `configure_logging()` once at process startup — in the FastAPI lifespan and in the Celery worker entrypoint. The function is **idempotent** (guarded by a `_automana_configured` flag on the root logger), so calling it more than once is safe.

```python
from automana.core.logging_config import configure_logging
configure_logging()
```

All module-level loggers created with `logging.getLogger(__name__)` automatically inherit the root handler — no per-module setup needed.

---

## Output format

Controlled by the `LOG_JSON` environment variable (default `"1"`):

### JSON (production default — `LOG_JSON=1`)

One JSON object per line, emitted to `stdout`. Fixed fields:

| Field | Source |
|---|---|
| `ts` | UTC ISO-8601 timestamp |
| `level` | Log level name (`INFO`, `WARNING`, …) |
| `logger` | `__name__` of the emitting module |
| `msg` | Formatted log message |
| `service` | `SERVICE_NAME` env var (default `"unknown"`) |
| `env` | `APP_ENV` env var (default `"dev"`) |
| `request_id` | Active HTTP request ID (see below) |
| `task_id` | Active Celery task ID (see below) |
| `service_path` | Active service registry path being executed |

Any keys passed via `extra={...}` are merged into the JSON payload automatically, as long as they don't collide with [Python's reserved `LogRecord` attributes](https://docs.python.org/3/library/logging.html#logrecord-attributes).

### Human-readable (`LOG_JSON=0`)

```
2026-04-01 12:00:00,000 INFO scryfall automana.core.services... request_id=abc task_id=xyz service_path=staging.scryfall.download_cards_bulk - Downloaded file
```

---

## Context variables

Context is stored in `contextvars.ContextVar` — each asyncio coroutine (request or Celery task) gets its own isolated copy, so concurrent requests never bleed context into each other.

| Variable | Setter | Getter | Set by |
|---|---|---|---|
| `request_id` | `set_request_id(v)` | `get_request_id()` | FastAPI middleware (per HTTP request) |
| `task_id` | `set_task_id(v)` | `get_task_id()` | Celery worker entrypoint (per task) |
| `service_path` | `set_service_path(v)` | `get_service_path()` | `ServiceManager` before dispatching a service call |

The `ContextFilter` (attached to the root handler) reads all three vars and stamps them onto every `LogRecord` automatically — you never need to pass them manually.

---

## Usage

```python
import logging
logger = logging.getLogger(__name__)

# Plain message
logger.info("Pipeline started")

# With extra fields (appear in the JSON payload)
logger.info("File downloaded", extra={"filename": out, "bytes": n})

# Warning / error
logger.warning("No URIs to download — skipping bulk step")
logger.error("Batch failed after retries", extra={"batch_index": i, "error": str(e)})
```

---

## Log level

Set at startup via the `LOG_LEVEL` env var (default `"INFO"`). Valid values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

```bash
LOG_LEVEL=DEBUG docker compose -f deploy/docker-compose.dev.yml up
```

---

## Observability integration

Structured logs complement the ops-schema pipeline tracking:

- `request_id` links all log lines for a single HTTP request.
- `task_id` links all log lines for a single Celery task execution.
- `service_path` identifies which service registry entry produced the log, matching the step name recorded in `ops.ingestion_run_steps`.

Querying logs by `service_path` + `task_id` gives you the full trace for a single pipeline step without needing a dedicated tracing backend.
