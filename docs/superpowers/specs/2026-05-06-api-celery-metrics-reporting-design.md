# API & Celery Metrics Reporting Service

**Date:** 2026-05-06  
**Status:** Design (pending review)

---

## Overview

This service tracks real-time metrics for API requests and Celery task executions, aggregates them hourly into a database, and generates a weekly Discord summary report. The report covers Monday–Sunday calendar weeks and is posted every Sunday at 21:00 (9 PM).

### Goals

1. Capture API request metrics (count, response times, error rates) per endpoint per hour
2. Capture Celery task metrics (execution times, success rates) per task name per hour
3. Store aggregated metrics for 60 days (retention window)
4. Generate a weekly Discord summary with top metrics and slowest endpoints/tasks

### Metrics Tracked

**API Requests (per endpoint, per hour):**
- Request count
- Response time: P95, median, max
- Error count and error rate
- Cache hit count and cache hit rate

**Celery Tasks (per task name, per hour):**
- Execution time: median, max
- Success count, failure count, success rate

---

## Database Schema

### New `reporting` Schema

```sql
CREATE SCHEMA IF NOT EXISTS reporting;
```

### `reporting.hourly_metrics` Table

Stores aggregated metrics, one row per (hour, metric_type, resource).

```sql
CREATE TABLE reporting.hourly_metrics (
  id BIGSERIAL PRIMARY KEY,
  hour TIMESTAMP NOT NULL,
  metric_type VARCHAR(20) NOT NULL, -- 'api_request' or 'celery_task'
  endpoint VARCHAR(255),  -- API endpoint path (e.g., '/api/collections/list'), NULL for Celery
  task_name VARCHAR(255), -- Celery task name (e.g., 'scryfall.download'), NULL for API
  status_code SMALLINT,   -- HTTP status code (e.g., 200, 404, 500), NULL for Celery
  
  -- Counts
  request_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  cache_hit_count INTEGER NOT NULL DEFAULT 0, -- Redis cache hits (API only)
  
  -- API response times (NULL for Celery)
  response_time_p95 FLOAT,
  response_time_median FLOAT,
  response_time_max FLOAT,
  
  -- Celery task metrics (NULL for API)
  celery_success_count INTEGER,
  celery_failure_count INTEGER,
  
  -- Derived metrics
  error_rate FLOAT, -- 0-1, computed as error_count / request_count
  cache_hit_rate FLOAT, -- 0-1, computed as cache_hit_count / request_count (API only)
  celery_success_rate FLOAT, -- 0-1, computed as success_count / (success_count + failure_count)
  
  -- Metadata
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  
  UNIQUE(hour, metric_type, endpoint, task_name, status_code)
);

CREATE INDEX idx_hourly_metrics_hour ON reporting.hourly_metrics(hour DESC);
CREATE INDEX idx_hourly_metrics_endpoint ON reporting.hourly_metrics(endpoint);
CREATE INDEX idx_hourly_metrics_task_name ON reporting.hourly_metrics(task_name);
```

### Data Retention

Weekly cleanup task deletes rows older than 60 days:

```sql
DELETE FROM reporting.hourly_metrics
WHERE created_at < NOW() - INTERVAL '60 days';
```

---

## Real-Time Metric Collection

### 1. API Request Middleware

Add a new middleware in `src/automana/api/middleware/metrics_middleware.py`:

- Captures: request start time, endpoint path, response status code, response time, **cache hit status**
- **In-memory buffer:** Stores metrics grouped by `(hour_bucket, endpoint, status_code)`
- Bucket resolution: **hourly** (e.g., all requests from 14:00–14:59 go into the same bucket)
- Buffer structure: `Dict[(int, str, int), MetricBucket]` where bucket contains counts, timings, and cache hits

**Cache Hit Tracking:** Services mark cache hits by setting a context variable or response attribute (e.g., `request.state.cache_hit = True`). The middleware reads this flag and increments the cache hit count.

**Pseudocode:**

```python
class MetricsMiddleware:
    def __init__(self):
        self.buffer = {}  # (hour, endpoint, status) -> MetricBucket
    
    async def __call__(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time
        
        hour_key = self._get_hour_key(start_time)
        endpoint = request.url.path
        status = response.status_code
        cache_hit = getattr(request.state, 'cache_hit', False)  # Read cache hit flag
        
        bucket_key = (hour_key, endpoint, status)
        if bucket_key not in self.buffer:
            self.buffer[bucket_key] = MetricBucket()
        
        self.buffer[bucket_key].add(elapsed, is_error=status >= 400, is_cache_hit=cache_hit)
        
        return response
```

**How to mark a cache hit in a service:**

```python
# In a service function
@ServiceRegistry.register("collections.get_by_id", db_repositories=["collections"])
async def get_collection_by_id(request: Request, collection_id: int, repo) -> Collection:
    result = await repo.get_cached(collection_id)
    if result:
        request.state.cache_hit = True  # Mark as cache hit
    return result
```

### 2. Celery Task Signal Hooks

Add signal handlers in `src/automana/worker/celery_metrics.py`:

- Hook into Celery signals: `task_prerun`, `task_success`, `task_failure`
- Captures: task name, execution time, outcome (success/failure)
- **In-memory buffer:** Same structure as API middleware, grouped by `(hour_bucket, task_name)`

**Pseudocode:**

```python
from celery.signals import task_prerun, task_success, task_failure

task_times = {}  # task_id -> start_time

@task_prerun.connect
def before_task(sender=None, task_id=None, **kwargs):
    task_times[task_id] = time.time()

@task_success.connect
def on_success(sender=None, result=None, task_id=None, **kwargs):
    if task_id in task_times:
        elapsed = time.time() - task_times[task_id]
        hour_key = _get_hour_key()
        bucket_key = (hour_key, sender.name)
        
        if bucket_key not in metrics_buffer:
            metrics_buffer[bucket_key] = CeleryMetricBucket()
        
        metrics_buffer[bucket_key].add_success(elapsed)
        del task_times[task_id]

@task_failure.connect
def on_failure(sender=None, task_id=None, **kwargs):
    if task_id in task_times:
        elapsed = time.time() - task_times[task_id]
        bucket_key = (hour_key, sender.name)
        metrics_buffer[bucket_key].add_failure(elapsed)
        del task_times[task_id]
```

---

## Hourly Aggregation & Database Flush

### Celery Beat Task: `ops.metrics.flush_hourly_metrics`

Runs every hour at minute 0 (e.g., 14:00, 15:00, etc.).

**Steps:**

1. Read in-memory buffer (API + Celery metrics)
2. For each bucket, compute aggregates:
   - **Counts:** sum of request/task counts and cache hit counts
   - **Response times:** compute P95, median, max from collected timings
   - **Rates:** 
     - error_rate = error_count / request_count
     - cache_hit_rate = cache_hit_count / request_count
     - success_rate = success_count / (success_count + failure_count)
3. Bulk-insert into `reporting.hourly_metrics` (using UPSERT on unique constraint)
4. Clear buffer for the completed hour
5. Log results (count of rows inserted, any errors)

**Error handling:**
- If flush fails, log error and retry (keep buffer in memory for next attempt)
- If buffer grows too large (memory pressure), trigger early flush

---

## Weekly Discord Report

### Celery Beat Task: `ops.metrics.discord_weekly_report`

Runs every Sunday at 21:00 (9 PM UTC, or configurable timezone).

**Steps:**

1. Query `reporting.hourly_metrics` for the **past calendar week (Monday 00:00 – Sunday 23:59)**
2. Extract metrics:
   - **API:** Group by endpoint, order by request_count DESC (show top 5–10), include p95, error_rate
   - **Celery:** Group by task_name, show median & max execution time, success rate
3. Format as markdown table (short, concise)
4. Post to Discord webhook via `DISCORD_WEBHOOK_URL` env var

**Table Format Example:**

```
📊 Weekly Metrics (Mon–Sun)

**API Endpoints**
| Endpoint | Hits | P95 (ms) | Error Rate | Cache Hit |
|----------|------|----------|-----------|-----------|
| /api/collections/list | 1,250 | 145 | 0.2% | 68% |
| /api/listings/detail | 890 | 210 | 1.1% | 42% |
| /api/ebay/sync | 340 | 520 | 5.3% | 12% |

**Celery Tasks**
| Task | Median (ms) | Max (ms) | Success Rate |
|------|-------------|---------|--------------|
| scryfall.download | 1200 | 4500 | 99.8% |
| mtgstock.sync | 850 | 2100 | 98.5% |
| pricing.load | 340 | 1200 | 99.2% |
```

**Error handling:**
- If Discord API call fails, log error and optionally retry with backoff
- If no data for the week, post a message saying "No metrics recorded this week"

---

## Data Retention & Cleanup

### Celery Beat Task: `ops.metrics.cleanup_old_metrics`

Runs weekly (or daily, TBD) to remove metrics older than 60 days.

```sql
DELETE FROM reporting.hourly_metrics
WHERE created_at < NOW() - INTERVAL '60 days';
```

Log: rows deleted, remaining row count.

---

## Configuration

All settings go into `core/settings.py`:

```python
class MetricsSettings:
    HOURLY_FLUSH_ENABLED: bool = True
    HOURLY_FLUSH_SCHEDULE: str = "*/1 * * * *"  # Every hour at minute 0
    
    WEEKLY_REPORT_ENABLED: bool = True
    WEEKLY_REPORT_SCHEDULE: str = "0 21 * * 0"  # Sunday 21:00 UTC
    
    DISCORD_WEBHOOK_URL: str = ""  # Set via env var
    
    METRICS_RETENTION_DAYS: int = 60
    CLEANUP_SCHEDULE: str = "0 2 * * 0"  # Weekly, Sunday 02:00
```

---

## Implementation Components

### New Files

1. **`src/automana/api/middleware/metrics_middleware.py`**
   - `MetricsMiddleware` class with buffer management
   - `MetricBucket` dataclass for storing timing data

2. **`src/automana/worker/celery_metrics.py`**
   - Signal handlers and buffer management
   - `CeleryMetricBucket` dataclass

3. **`src/automana/core/services/ops/metrics_service.py`**
   - `flush_hourly_metrics()` service
   - `discord_weekly_report()` service
   - `cleanup_old_metrics()` service

4. **`database/SQL/migrations/[timestamp]_create_reporting_schema.sql`**
   - Schema and table creation with indexes

### Modified Files

1. **`src/automana/api/main.py`**
   - Register `MetricsMiddleware` in the FastAPI app

2. **`src/automana/worker/celery_worker.py`**
   - Import and register signal handlers

3. **`src/automana/core/settings.py`**
   - Add `MetricsSettings` class with env var bindings

4. **`src/automana/core/service_registry.py`**
   - Register the three new services (`metrics.flush_hourly_metrics`, `metrics.discord_weekly_report`, `metrics.cleanup_old_metrics`)

---

## Error Handling & Edge Cases

1. **Middleware performance:** Metric capture should have minimal overhead (~1–2ms per request). Use fast in-memory structures.

2. **Buffer overflow:** If buffer grows beyond a threshold (e.g., 10K buckets), log a warning and consider early flush.

3. **Celery task timeouts:** If a task doesn't emit success/failure signal, metrics are lost. Document this limitation; consider adding a "long-running task detector" in future.

4. **Discord downtime:** If Discord webhook is unreachable, log error and skip that week's report (don't retry aggressively to avoid spam).

5. **Database unavailability:** If the flush task fails to insert, keep metrics in memory and retry on next hourly tick. Document max buffer size.

6. **Timezone handling:** Use UTC internally; display timezone can be configurable in settings.

---

## Testing

- **Unit tests:** Test `MetricBucket`, aggregation logic, Discord message formatting
- **Integration tests:** Spin up a test Redis/Celery, fire a few tasks, verify metrics table
- **Manual:** Send test requests to endpoints, verify hourly flush produces correct rows
- **Discord:** Test webhook posting with a staging Discord server

---

## Future Enhancements

- Percentile computation (P50, P75, P90, P99 in addition to P95)
- Per-user/tenant metrics (if AutoMana adds multi-tenancy)
- Real-time dashboard (WebSocket endpoint for live metrics)
- Anomaly detection (alert if error rate exceeds threshold)
- Detailed per-endpoint breakdown (by HTTP method, auth status, etc.)

---

## Questions for Implementation

1. Should `DISCORD_WEBHOOK_URL` be stored as a secret in the database or as an env var?
2. Should the weekly report be timezone-aware (e.g., report week in user's local TZ)?
3. Should we also log metrics to a time-series database (InfluxDB, Prometheus) for advanced queries?

