# Metrics Reporting Service

## Overview

AutoMana's metrics reporting service provides real-time collection, aggregation, and reporting of API request and Celery task execution metrics. The system captures performance data, error rates, cache hit rates, and task success rates, storing them for analysis and generating weekly Discord summaries.

**Key Features:**
- Real-time metric collection with minimal overhead (~1-2ms per request)
- Hourly aggregation and database storage
- Weekly Discord reports with top endpoints, slowest tasks, and success rates
- 60-day automatic retention and cleanup
- Thread-safe in-memory buffering
- P95, median, and max response time metrics

---

## Architecture

### Data Flow

```
API Requests / Celery Tasks
    ↓
Middleware / Signal Hooks (real-time capture)
    ↓
MetricsBuffer (in-memory aggregation by hour)
    ↓
Hourly Flush Service (aggregates to database)
    ↓
reporting.hourly_metrics table (persistent storage)
    ↓
Weekly Discord Report Service (generates summaries)
    ↓
Discord Channel
```

### Components

#### 1. Real-Time Collection Layer

**API Requests (FastAPI Middleware)**
- File: `src/automana/api/middleware/metrics_middleware.py`
- Captures: endpoint path, HTTP status code, response time, cache hit flag
- Triggers on every HTTP request before routing

**Celery Tasks (Signal Hooks)**
- File: `src/automana/worker/celery_metrics.py`
- Captures: task name, execution time, success/failure outcome
- Triggers on task prerun, success, and failure signals

#### 2. Buffering Layer

**MetricsBuffer Singleton**
- File: `src/automana/core/metrics/buffer.py`
- Stores metrics in memory, grouped by hour
- Thread-safe with locking mechanisms
- Flushed hourly to database

**Metric Buckets**
- File: `src/automana/core/metrics/bucket.py`
- `MetricBucket`: aggregates API request metrics
- `CeleryMetricBucket`: aggregates task execution metrics
- Computes percentiles, medians, error rates, success rates

#### 3. Database Layer

**Schema**
- Location: `database/SQL/migrations/migration_24_reporting_schema.sql`
- Table: `reporting.hourly_metrics`
- Stores: hourly aggregated metrics for all endpoints and tasks

**Repository**
- File: `src/automana/core/repositories/metrics_repositories/metrics_repository.py`
- Async methods for inserting, querying, and deleting metrics

#### 4. Services

**`ops.metrics.flush_hourly_metrics`**
- Runs hourly (cron: `0 * * * *`)
- Flushes in-memory buffer to database
- Computes aggregates and inserts rows

**`ops.metrics.discord_weekly_report`**
- Runs weekly (cron: `0 21 * * 0` — Sunday 9 PM UTC)
- Queries database for past week's data (Mon–Sun)
- Generates markdown table with top endpoints and tasks
- Posts to Discord webhook

**`ops.metrics.cleanup_old_metrics`**
- Runs weekly (cron: `0 2 * * 0` — Sunday 2 AM UTC)
- Deletes metrics older than 60 days
- Maintains database size

---

## Metrics Captured

### API Request Metrics

Per endpoint per hour:

| Metric | Type | Description |
|--------|------|-------------|
| `request_count` | Integer | Total requests to endpoint |
| `error_count` | Integer | Requests with status >= 400 |
| `cache_hit_count` | Integer | Requests served from cache |
| `error_rate` | Float (0-1) | error_count / request_count |
| `cache_hit_rate` | Float (0-1) | cache_hit_count / request_count |
| `response_time_p95` | Float (ms) | 95th percentile response time |
| `response_time_median` | Float (ms) | Median response time |
| `response_time_max` | Float (ms) | Maximum response time |

**How to Mark Cache Hits in Services:**

In any route handler or service function, set the cache hit flag when serving from cache:

```python
@app.get("/api/collections/{id}")
async def get_collection(id: int, request: Request, repo):
    result = await repo.get_cached(id)
    if result:
        request.state.cache_hit = True  # Mark as cache hit
    return result
```

The middleware will read this flag and record a cache hit in the metrics.

### Celery Task Metrics

Per task name per hour:

| Metric | Type | Description |
|--------|------|-------------|
| `celery_success_count` | Integer | Successful task executions |
| `celery_failure_count` | Integer | Failed task executions |
| `celery_success_rate` | Float (0-1) | success_count / (success_count + failure_count) |
| `median_execution_time` | Float (ms) | Median task execution time |
| `max_execution_time` | Float (ms) | Maximum task execution time |

**Automatic Capture:**

Signal handlers automatically capture task metrics when tasks execute. No code changes needed—just ensure `setup_celery_metrics()` is called at worker startup (already integrated in `src/automana/worker/main.py`).

---

## Configuration

All settings are in `src/automana/core/settings.py` under `MetricsSettings`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_HOURLY_FLUSH_ENABLED` | `true` | Enable hourly metrics flush |
| `METRICS_HOURLY_FLUSH_SCHEDULE` | `0 * * * *` | Cron schedule for hourly flush |
| `METRICS_WEEKLY_REPORT_ENABLED` | `true` | Enable weekly Discord report |
| `METRICS_WEEKLY_REPORT_SCHEDULE` | `0 21 * * 0` | Cron schedule (Sunday 9 PM UTC) |
| `METRICS_DISCORD_WEBHOOK_URL` | `` | Discord webhook URL for reports |
| `METRICS_RETENTION_DAYS` | `60` | Days to retain metrics before cleanup |
| `METRICS_CLEANUP_SCHEDULE` | `0 2 * * 0` | Cron schedule for cleanup (Sunday 2 AM UTC) |

### Setting Discord Webhook URL

1. Create a Discord webhook in your server
2. Set the environment variable:
   ```bash
   export METRICS_DISCORD_WEBHOOK_URL="https://discordapp.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
   ```
3. Weekly reports will now be posted to Discord

---

## Running Services Manually

### Trigger Hourly Flush

```bash
automana-run ops.metrics.flush_hourly_metrics
```

**Output:** Returns count of rows inserted to database.

### Generate Weekly Report

```bash
automana-run ops.metrics.discord_weekly_report
```

**Output:** Posts table to Discord (if webhook configured), or returns `"no_data"` if no metrics recorded.

### Run Cleanup

```bash
automana-run ops.metrics.cleanup_old_metrics
```

**Output:** Returns count of rows deleted (older than 60 days).

---

## Querying Metrics

### Access the Database

Connect to PostgreSQL:

```bash
psql -h localhost -p 5433 -U automana_admin -d automana
```

### Basic Queries

**Count total metrics recorded:**

```sql
SELECT COUNT(*) FROM reporting.hourly_metrics;
```

**Top endpoints by request count (this week):**

```sql
SELECT 
  endpoint, 
  SUM(request_count) as total_requests,
  AVG(response_time_p95) as avg_p95,
  AVG(error_rate) as avg_error_rate,
  AVG(cache_hit_rate) as avg_cache_hit
FROM reporting.hourly_metrics
WHERE metric_type = 'api_request'
  AND hour >= NOW() - INTERVAL '7 days'
GROUP BY endpoint
ORDER BY total_requests DESC
LIMIT 10;
```

**Top slow endpoints (by P95):**

```sql
SELECT 
  endpoint,
  response_time_p95,
  request_count
FROM reporting.hourly_metrics
WHERE metric_type = 'api_request'
  AND response_time_p95 IS NOT NULL
ORDER BY response_time_p95 DESC
LIMIT 10;
```

**Celery task success rates (this week):**

```sql
SELECT 
  task_name,
  SUM(celery_success_count) as successes,
  SUM(celery_failure_count) as failures,
  ROUND(100.0 * SUM(celery_success_count) / (SUM(celery_success_count) + SUM(celery_failure_count)), 2) as success_rate_pct
FROM reporting.hourly_metrics
WHERE metric_type = 'celery_task'
  AND hour >= NOW() - INTERVAL '7 days'
GROUP BY task_name
ORDER BY success_rate_pct ASC;
```

---

## Weekly Discord Report Format

The weekly report posts a markdown table with this structure:

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

---

## Performance Considerations

### Middleware Overhead

- **Per-request cost:** ~1-2ms (time tracking + buffer operation)
- **Buffer memory:** Minimal (~10KB per unique endpoint/task combination per hour)
- **Thread-safety:** Uses locks only during buffer access (fast path)

### Database Impact

- **Insert pattern:** Bulk insert hourly (~100-1000 rows per hour depending on traffic)
- **Index efficiency:** Indexes on hour (DESC), endpoint, task_name for fast queries
- **Retention:** Automatic cleanup keeps table size bounded (60-day rolling window)

### Best Practices

1. **Monitor buffer size:** Check for stuck tasks that don't emit success/failure signals
2. **Verify Discord webhook:** Test with manual service trigger
3. **Archive old reports:** Consider exporting metrics to data warehouse for long-term analysis
4. **Alert on errors:** Set up Discord alerts for high error rates (future enhancement)

---

## Troubleshooting

### Metrics Not Appearing in Database

1. **Verify middleware is registered:**
   ```bash
   grep -n "MetricsMiddleware" src/automana/api/main.py
   ```

2. **Verify signal handlers are registered:**
   ```bash
   grep -n "setup_celery_metrics" src/automana/worker/main.py
   ```

3. **Check buffer state:**
   ```python
   from automana.core.metrics.buffer import MetricsBuffer
   buffer = MetricsBuffer.get_instance()
   api_size, celery_size = buffer.size()
   print(f"API buckets: {api_size}, Celery buckets: {celery_size}")
   ```

4. **Manually trigger flush:**
   ```bash
   automana-run ops.metrics.flush_hourly_metrics
   ```

### Discord Report Not Posting

1. **Verify webhook URL is set:**
   ```bash
   echo $METRICS_DISCORD_WEBHOOK_URL
   ```

2. **Test Discord connection:**
   ```bash
   automana-run ops.metrics.discord_weekly_report
   ```

3. **Check service logs:**
   ```bash
   docker logs automana-api-dev 2>&1 | grep -i discord
   ```

### Slow Queries

1. **Verify indices exist:**
   ```sql
   SELECT * FROM pg_indexes WHERE schemaname = 'reporting';
   ```

2. **Check query plan:**
   ```sql
   EXPLAIN ANALYZE SELECT ... FROM reporting.hourly_metrics WHERE hour >= NOW() - INTERVAL '7 days';
   ```

3. **Rebuild indices if needed:**
   ```sql
   REINDEX TABLE reporting.hourly_metrics;
   ```

---

## Future Enhancements

- **Percentiles:** P50, P75, P90, P99 (in addition to P95)
- **Anomaly detection:** Alert when error rate exceeds threshold
- **Custom alerts:** Slack/email notifications for SLA violations
- **Real-time dashboard:** WebSocket endpoint for live metrics
- **Tenant-aware metrics:** Per-user or per-org breakdowns
- **Time-series database:** Export to InfluxDB for advanced queries
- **Heatmaps:** Visualize request patterns over time
- **Correlation analysis:** Find relationships between metrics (e.g., error rate vs cache hit rate)

---

## Testing

### Unit Tests

```bash
pytest tests/unit/core/metrics/ -v
pytest tests/unit/api/middleware/test_metrics_middleware.py -v
pytest tests/unit/worker/test_celery_metrics.py -v
```

### Integration Tests

```bash
pytest tests/integration/test_metrics_e2e.py -v
```

### Manual Testing

1. Send requests to API endpoints
2. Trigger hourly flush: `automana-run ops.metrics.flush_hourly_metrics`
3. Verify data in database: `SELECT COUNT(*) FROM reporting.hourly_metrics;`
4. Generate report: `automana-run ops.metrics.discord_weekly_report`

---

## Implementation Details

### Files

| File | Purpose |
|------|---------|
| `src/automana/core/metrics/bucket.py` | MetricBucket and CeleryMetricBucket dataclasses |
| `src/automana/core/metrics/buffer.py` | MetricsBuffer singleton |
| `src/automana/api/middleware/metrics_middleware.py` | FastAPI middleware for API metrics |
| `src/automana/worker/celery_metrics.py` | Celery signal handlers |
| `src/automana/core/services/ops/metrics_service.py` | Flush, report, and cleanup services |
| `src/automana/core/repositories/metrics_repositories/metrics_repository.py` | Database repository |
| `database/SQL/migrations/migration_24_reporting_schema.sql` | Database schema |

### Key Design Decisions

1. **In-memory buffering:** Reduces database writes while maintaining accuracy
2. **Hourly buckets:** Balances granularity with storage efficiency
3. **Singleton buffer:** Ensures consistent state across requests/tasks
4. **Thread-safe locking:** Protects against race conditions in async context
5. **Discord reporting:** Provides visibility to team without dashboarding infrastructure
6. **60-day retention:** Balances historical context with database size

---

## References

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — System architecture and patterns
- [`docs/LOGGING.md`](LOGGING.md) — Logging configuration and usage
- [`docs/OPERATIONS.md`](OPERATIONS.md) — Operations and monitoring
- [`docs/CLI_RUN_SERVICE.md`](CLI_RUN_SERVICE.md) — Running services via CLI
