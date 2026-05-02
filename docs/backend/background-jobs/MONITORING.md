# Monitoring Background Jobs

This document covers observability, health checks, and debugging strategies for background jobs (Celery tasks and pipelines). It covers metrics collection, logging, error tracking, performance analysis, and on-demand diagnostics.

---

## Table of Contents

1. [Overview](#overview)
2. [Metrics Collection (MetricRegistry)](#metrics-collection-metricregistry)
3. [Logging from Background Jobs](#logging-from-background-jobs)
4. [Error Tracking and Alerts](#error-tracking-and-alerts)
5. [Performance Metrics](#performance-metrics)
6. [Health Checks](#health-checks)
7. [Debugging Background Jobs](#debugging-background-jobs)
8. [On-Demand Diagnostics](#on-demand-diagnostics)

---

## Overview

### Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│              Background Job                         │
│  (Celery task → run_service dispatcher)            │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┴──────────┬──────────────┐
        │                     │              │
        v                     v              v
    Logging              Ops Tracking    Metrics
    (JSON stdout)        (ops schema)    (MetricRegistry)
        │                     │              │
        │                     │              │
        v                     v              v
   ┌────────────┐    ┌──────────────┐  ┌─────────────┐
   │ JSON logs  │    │ ops tables:  │  │ Metric      │
   │ (stdout)   │    │ •runs        │  │ services    │
   │ - msg      │    │ •steps       │  │ (async fn)  │
   │ - level    │    │ •metrics     │  │ - queries   │
   │ - extra    │    │              │  │ - severity  │
   └──────┬─────┘    └──────┬───────┘  │ - thresholds│
          │                 │          └──────┬──────┘
          │                 │                 │
          └─────────┬───────┴─────────┬──────┘
                    │                 │
                    v                 v
              ┌──────────────────────────────┐
              │  Monitoring & Alerting       │
              │  (ELK, Datadog, etc.)        │
              │  or CLI-based inspection     │
              └──────────────────────────────┘
```

---

## Metrics Collection (MetricRegistry)

### What is MetricRegistry?

`MetricRegistry` is a decorator-based system for defining and running **sanity-report metrics**. Unlike application metrics (request latency, throughput), sanity metrics are **read-only diagnostics** that query specific slices of the DB and return a single scalar value + optional context.

**Key sources:**
- [`src/automana/core/metrics/`](../../src/automana/core/metrics/) — Metric implementations
- [`src/automana/core/metrics/__init__.py`](../../src/automana/core/metrics/__init__.py) — MetricRegistry, MetricResult, Severity, Threshold classes
- [`docs/METRICS_REGISTRY.md`](../../METRICS_REGISTRY.md) — Complete MetricRegistry reference

### Metric Example: Card Catalog Health

```python
from automana.core.metrics import MetricRegistry, MetricResult, Severity, Threshold

@MetricRegistry.register(
    path="card_catalog.identifier_coverage.scryfall_id",
    category="health",
    description="% of card_version rows with a scryfall_id in card_external_identifier",
    severity=Threshold(warn=99, error=95, direction="lower_is_worse"),
    db_repositories=["card_catalog"],
)
async def scryfall_id_coverage(
    card_catalog_repository: CardCatalogRepository
) -> MetricResult:
    """Return % coverage of scryfall_id across all card_version rows."""
    covered = await card_catalog_repository.count_with_scryfall_id()
    total = await card_catalog_repository.count_all_card_versions()
    
    pct = (covered / total * 100) if total > 0 else 0.0
    
    return MetricResult(
        row_count=pct,
        details={"covered": covered, "total": total}
    )
```

### Metric Severity

Each metric has a **severity rule** that evaluates the row_count:

```python
# Threshold-based (for numeric metrics)
severity=Threshold(
    warn=99,           # WARN if ≤ 99
    error=95,          # ERROR if ≤ 95
    direction="lower_is_worse"  # Lower is worse (coverage)
)

# Or callable (for non-numeric)
def _severity_fn(value: str) -> Severity:
    if value == "success":
        return Severity.OK
    elif value in ("running", "partial"):
        return Severity.WARN
    else:
        return Severity.ERROR

severity=_severity_fn
```

**Result:**
```
row_count=98% → WARN (between 95 and 99)
row_count=90% → ERROR (below 95)
row_count=100% → OK
```

### Running Metrics

Metrics are typically run via **integrity report services** (e.g., `ops.integrity.card_catalog_report`):

```bash
# View the full report
automana-run ops.integrity.card_catalog_report

# Filter by category (health checks only)
automana-run ops.integrity.card_catalog_report --category health

# Run a single metric
automana-run ops.integrity.card_catalog_report \
  --metrics card_catalog.identifier_coverage.scryfall_id

# Comma-separated list
automana-run ops.integrity.pricing_report \
  --metrics pricing.freshness.price_observation_max_age_days,pricing.coverage.min_per_source_observation_coverage_pct
```

### Sample Report Output

```
check_set:    card_catalog_report
total_checks: 8    errors: 1    warnings: 0    ok: 7

card_catalog.identifier_coverage.scryfall_id          ok    100.0   covered=113776 total=113776
card_catalog.identifier_coverage.oracle_id         ERROR     32.73  covered=37236 total=113776   ← real gap
card_catalog.identifier_coverage.tcgplayer_id         ok     84.92  covered=96618 total=113776
card_catalog.identifier_coverage.cardmarket_id        ok     81.79  covered=93060 total=113776
```

### Key Metric Families

| Family | Service | Schedule | Watches |
|--------|---------|----------|---------|
| `card_catalog.*` | `ops.integrity.card_catalog_report` | Daily @ 04:15 AEST | Identifier coverage, orphan unique cards, collision detection |
| `pricing.*` | `ops.integrity.pricing_report` | Hourly @ :42 | Price freshness, per-source coverage, soft-integrity, staging drain |
| `mtgstock.*` | `ops.integrity.mtgstock_report` | Ad-hoc or per-run | Per-pipeline ingestion metrics |

See [`docs/HEALTH_METRICS.md`](../../HEALTH_METRICS.md) for exhaustive metric reference.

---

## Logging from Background Jobs

### Structured JSON Logging

All background job logging is **structured JSON** via the `JsonFormatter`:

**File:** `src/automana/core/logging_config.py`

```python
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "service": os.getenv("SERVICE_NAME", "unknown"),
            "env": os.getenv("APP_ENV", "dev"),
            "request_id": getattr(record, "request_id", None),  # None for tasks
            "task_id": getattr(record, "task_id", None),        # Set by Celery
            "service_path": getattr(record, "service_path", None),  # Set by run_service
            # ... any extra keys passed via extra={}
        }
        return json.dumps(payload, default=str)
```

### Logging Conventions

Follow these rules (from CLAUDE.md):

1. **Keep the message static** — put all context in `extra={}`:

   ```python
   # ✅ Good
   logger.info("cards_loaded", extra={"count": 42, "duration_sec": 3.2})
   
   # ❌ Bad
   logger.info(f"Loaded {count} cards in {duration_sec} seconds")
   ```

2. **Don't use reserved LogRecord attributes** as extra keys:

   ```python
   # ❌ Bad (conflicts with Python logging)
   logger.info("msg", extra={"filename": "x.py", "lineno": 123})
   
   # ✅ Good (unambiguous names)
   logger.info("msg", extra={"file": "x.py", "line": 123})
   ```

3. **Never use logging.basicConfig()** in worker code — it would create duplicate handlers.

### Context Variables

Three context variables are automatically injected into every log:

**File:** `src/automana/core/logging_context.py`

| Variable | Set by | Read by | Purpose |
|----------|--------|---------|---------|
| `request_id` | FastAPI middleware | ContextFilter | Links logs from a single HTTP request |
| `task_id` | Celery worker | ContextFilter | Links logs from a single Celery task |
| `service_path` | ServiceManager | ContextFilter | Links logs from a single service call |

**Example:**

```python
# In a service
async def download_file(api_repository, file_path):
    logger.info("starting_download", extra={"file_path": file_path})
    data = await api_repository.get(file_path)
    logger.info("download_complete", extra={"bytes": len(data)})
```

Produces:

```json
{"ts":"2026-03-29T02:00:00Z","level":"INFO","logger":"automana.core.services...","msg":"starting_download","file_path":"...","task_id":"abc123...","service_path":"staging.scryfall.download_cards_bulk"}
{"ts":"2026-03-29T02:00:02Z","level":"INFO","logger":"automana.core.services...","msg":"download_complete","bytes":1024,"task_id":"abc123...","service_path":"staging.scryfall.download_cards_bulk"}
```

### Log Levels

- `DEBUG`: Per-step dispatcher wiring (fired once per service call, can be noisy)
- `INFO`: Normal progress (pipeline started, step completed, etc.)
- `WARNING`: Recoverable issue (partial batch failure, retry attempt)
- `ERROR`: Unrecoverable error (service failed, unhandled exception)
- `CRITICAL`: System-level failure (DB pool exhausted, memory error)

### Viewing Logs

```bash
# Follow logs from a running worker
docker compose -f deploy/docker-compose.dev.yml logs -f celery-worker

# Search for a task_id
docker compose -f deploy/docker-compose.dev.yml logs celery-worker | grep "task_id=abc123"

# Parse JSON logs and filter by level
docker compose -f deploy/docker-compose.dev.yml logs celery-worker \
  | jq 'select(.level == "ERROR")'
```

---

## Error Tracking and Alerts

### Ops Schema Error Recording

When a pipeline step fails, the error is captured in the `ops` schema:

```sql
-- ops.ingestion_runs (after failure)
status = 'failed'
current_step = 'card_catalog.card.process_large_json'
error_code = 'step_failed'
error_details = {
    "message": "FileNotFoundError: /path/to/cards.json not found",
    "step": "card_catalog.card.process_large_json"
}
```

### Querying Failed Runs

```sql
-- All failed runs
SELECT
    id, pipeline_name, source_name,
    current_step, error_code, error_details,
    finished_at
FROM ops.ingestion_runs
WHERE status = 'failed'
ORDER BY finished_at DESC
LIMIT 20;

-- Failed runs in the last 24 hours
SELECT
    id, pipeline_name, source_name, current_step,
    error_details ->> 'message' as error_msg,
    EXTRACT(EPOCH FROM (now() - finished_at)) / 3600 as hours_ago
FROM ops.ingestion_runs
WHERE status = 'failed'
  AND finished_at > now() - INTERVAL '24 hours'
ORDER BY finished_at DESC;
```

### Alert Rules (Example)

For a production monitoring system (e.g., Datadog), set up alerts:

| Alert | Condition | Action |
|-------|-----------|--------|
| Pipeline failed | `ops.ingestion_runs.status = 'failed'` | Slack + page on-call |
| High error rate | `errors_per_min > 5` | Email |
| Metric threshold breached | `card_catalog.identifier_coverage.scryfall_id < 95%` | Slack warning |
| Stalled pipeline | No successful run in 25 hours | Slack alert |

### Error Handling Strategy

**For transient errors** (network timeout, DB connection reset):
- Retry inside the service (via `@retry` decorator)
- If all retries fail, let the exception propagate
- The entire run fails; can be re-triggered manually

**For non-transient errors** (invalid JSON, missing field):
- Log at ERROR level with full context
- Fail the step immediately
- Operator inspects logs and fixes the issue

**For partial failures** (e.g., 99 out of 100 rows inserted):
- Log the counts
- Return a dict with `successful_count` and `failed_items`
- Downstream steps decide: continue or abort

---

## Performance Metrics

### Measuring Step Duration

Use logging to track elapsed time per step:

```python
import time

async def process_large_json(card_repository, file_path):
    start = time.time()
    
    async with track_step(ops_repository, ingestion_run_id, "process_large_json"):
        count = await card_repository.load_from_file(file_path)
        elapsed = time.time() - start
        
        logger.info("step_complete", extra={
            "file_path": file_path,
            "cards_loaded": count,
            "duration_sec": elapsed,
            "rate_per_sec": count / elapsed if elapsed > 0 else 0,
        })
        
        return {"cards_loaded": count}
```

Logs:

```json
{"msg":"step_complete","duration_sec":12.5,"cards_loaded":50000,"rate_per_sec":4000}
```

### Pipeline Throughput

Query the ops tables to compute throughput:

```sql
-- Daily ingestion volume (by pipeline)
SELECT
    DATE_TRUNC('day', started_at) as day,
    pipeline_name,
    COUNT(*) as run_count,
    SUM((finished_at - started_at)) / COUNT(*) as avg_duration,
    COUNT(CASE WHEN status = 'success' THEN 1 END) as success_count,
    COUNT(CASE WHEN status = 'failed' THEN 1 END) as fail_count
FROM ops.ingestion_runs
WHERE started_at > now() - INTERVAL '7 days'
GROUP BY day, pipeline_name
ORDER BY day DESC, pipeline_name;
```

### Celery Task Queue Depth

Use `redis-cli` to inspect the queue:

```bash
# Connect to Redis
redis-cli -h localhost -p 6379 -n 0

# Check queue length
LLEN celery
LLEN celery:0

# View queued task names
LRANGE celery 0 10
```

### Worker Pool Utilization

```bash
# Number of active workers
celery -A automana.worker.main:app inspect active_queues

# Tasks currently executing
celery -A automana.worker.main:app inspect active

# Worker stats (memory, pool size)
celery -A automana.worker.main:app inspect stats
```

---

## Health Checks

### Pipeline Health Alert Task

A scheduled task runs periodic health checks:

```python
@shared_task(name="pipeline_health_alert_task", bind=True)
def pipeline_health_alert_task(self):
    """Run pipeline health checks twice daily."""
    result = run_service.apply_async(
        args=["ops.pipeline_services.run_alert_check"],
    ).get()
    
    if result and result.get("alerts"):
        # Send Slack notification, page on-call, etc.
        logger.warning("pipeline_health_alert", extra=result["alerts"])
```

### Running Health Checks Manually

```bash
# Check card catalog health
automana-run ops.integrity.card_catalog_report

# Check pricing health
automana-run ops.integrity.pricing_report

# Check MTGStock pipeline metrics (for a specific run)
automana-run ops.integrity.mtgstock_report --ingestion_run_id 42

# Filter to errors only
automana-run ops.integrity.card_catalog_report --category health 2>/dev/null \
  | grep -v "^{" | grep ERROR
```

### SLA Monitoring

```sql
-- Yesterday's pipeline success rate
SELECT
    pipeline_name,
    COUNT(*) as total_runs,
    COUNT(CASE WHEN status = 'success' THEN 1 END) as successful,
    ROUND(100.0 * COUNT(CASE WHEN status = 'success' THEN 1 END) / COUNT(*), 2) as success_pct
FROM ops.ingestion_runs
WHERE DATE_TRUNC('day', started_at) = CURRENT_DATE - INTERVAL '1 day'
GROUP BY pipeline_name
ORDER BY pipeline_name;
```

---

## Debugging Background Jobs

### 1. Check Recent Runs

```sql
SELECT id, pipeline_name, status, current_step, started_at, finished_at, error_code, error_details
FROM ops.ingestion_runs
ORDER BY started_at DESC
LIMIT 10;
```

### 2. Drill into a Failed Run

```sql
-- Examine the run
SELECT * FROM ops.ingestion_runs WHERE id = 42;

-- View all steps for this run
SELECT step_name, status, started_at, finished_at, error_details
FROM ops.ingestion_run_steps
WHERE ingestion_run_id = 42
ORDER BY started_at;

-- View metrics for this run
SELECT key, value
FROM ops.ingestion_run_metrics
WHERE ingestion_run_id = 42;
```

### 3. Search Logs by Task ID

```bash
# Get the celery_task_id from the run
psql automana -c "SELECT celery_task_id FROM ops.ingestion_runs WHERE id = 42"

# Search logs
docker compose -f deploy/docker-compose.dev.yml logs celery-worker \
  | grep "task_id=<CELERY_TASK_ID>"
```

### 4. Inspect Active Tasks

```bash
# See what's currently running
celery -A automana.worker.main:app inspect active

# Get task details
celery -A automana.worker.main:app inspect reserved
```

### 5. Replay a Failed Task

```bash
# Get the task ID from the run
TASK_ID=$(psql automana -tAc "SELECT celery_task_id FROM ops.ingestion_runs WHERE id = 42")

# Re-run the same task
celery -A automana.worker.main:app call automana.worker.tasks.pipelines.daily_scryfall_data_pipeline
```

---

## On-Demand Diagnostics

### Scryfall Identifier Audit

For investigating identifier-shape questions, run an on-demand audit that streams a Scryfall raw bulk JSON file and compares against the DB row-for-row:

```bash
automana-run ops.audit.scryfall_identifier_coverage --file_path /path/to/cards.json
```

This is a **read-only diagnostic** that does not modify any data — it just flags discrepancies.

### Database Size Analysis

```sql
-- Table sizes in the card_catalog schema
SELECT
    schemaname, tablename,
    ROUND(pg_total_relation_size(schemaname || '.' || tablename) / 1024 / 1024) as size_mb
FROM pg_tables
WHERE schemaname = 'card_catalog'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;

-- Pricing schema sizes
SELECT
    schemaname, tablename,
    ROUND(pg_total_relation_size(schemaname || '.' || tablename) / 1024 / 1024) as size_mb
FROM pg_tables
WHERE schemaname = 'pricing'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;
```

### Index Utilization

```sql
-- Unused indexes (potential cleanup targets)
SELECT
    schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Slow Query Log

Enable the PostgreSQL slow query log:

```sql
-- Set slow query threshold to 1 second
SET log_min_duration_statement = 1000;

-- Check current log
SHOW log_statement;
```

Then monitor logs:

```bash
docker exec automana-postgres-dev tail -f /var/log/postgresql/postgres.log
```

### Memory Usage

```bash
# Memory per worker
docker compose -f deploy/docker-compose.dev.yml stats celery-worker

# Memory per connection
psql automana -c "SELECT usename, count(*) as connections FROM pg_stat_activity GROUP BY usename"
```

---

## Best Practices

1. **Instrument every significant step** — Use `track_step()` and structured logging consistently.

2. **Return dicts from services** — Every service should return a dict so context can flow to the next step.

3. **Keep messages static** — Put all context in `extra={}` for JSON parsing.

4. **Set alert thresholds** — For each metric, define warning and error thresholds based on SLAs.

5. **Review logs post-incident** — After a pipeline failure, review the logs to understand the root cause.

6. **Schedule health checks** — Run metric reports on a cadence (daily for card_catalog, hourly for pricing).

7. **Monitor the monitors** — Set up alerts if health checks themselves are stalling.

8. **Archive old runs** — Regularly archive or delete old `ops` table rows to keep scans fast.

---

## See Also

- [`docs/LOGGING.md`](../../LOGGING.md) — Logging setup and context
- [`docs/METRICS_REGISTRY.md`](../../METRICS_REGISTRY.md) — Metric registration and execution
- [`docs/HEALTH_METRICS.md`](../../HEALTH_METRICS.md) — Exhaustive metric reference
- [`docs/backend/background-jobs/CELERY_ARCHITECTURE.md`](CELERY_ARCHITECTURE.md) — Celery framework
- [`docs/backend/background-jobs/PIPELINE_PATTERNS.md`](PIPELINE_PATTERNS.md) — Pipeline patterns and track_step
- [`docs/OPERATIONS.md`](../../OPERATIONS.md) — Day-2 operations runbook
- [Flower (Celery monitoring)](https://flower.readthedocs.io/)
