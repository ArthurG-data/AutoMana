# Performance

AutoMana is designed for efficient handling of large card collections, ETL pipelines, and concurrent user requests. This document covers performance optimization strategies, bottleneck analysis, and monitoring.

**Related files:**
- `docs/METRICS_REGISTRY.md` — Health metrics and sanity checks
- `docs/HEALTH_METRICS.md` — Database health metrics and audit strategies
- `deploy/docker-compose.prod.yml` — Concurrency settings (Celery workers, etc.)

---

## Bottleneck Analysis Methodology

Before optimizing, identify where time is actually spent.

### 1. Application-level profiling

Use Python's `cProfile` or `py-spy` to measure function execution time:

```python
import cProfile
import pstats
from io import StringIO

# Profile a function
profiler = cProfile.Profile()
profiler.enable()

# ... your code ...

profiler.disable()
stats = pstats.Stats(profiler, stream=StringIO())
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

**In production, use `py-spy`:**

```bash
# Attach to running process
py-spy record -o profile.svg -p <pid>

# Generate flamegraph
flamegraph.pl profile.svg > flamegraph.html
```

### 2. Database query analysis

Enable PostgreSQL slow query logging:

```sql
-- In PostgreSQL
SET log_min_duration_statement = 1000;  -- Log queries > 1 second
```

**In Docker:**

```yaml
postgres:
  environment:
    POSTGRES_INITDB_ARGS: "-c log_min_duration_statement=1000"
```

**Query logs appear in:**

```bash
docker compose logs postgres | grep "duration: "
```

### 3. Request-level metrics

Log request duration and database time:

```python
import time
import logging

logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_request_metrics(request: Request, call_next):
    start = time.perf_counter()
    db_time = 0
    
    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        
        logger.info("http_request", extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "elapsed_ms": int(elapsed * 1000),
            "db_time_ms": int(db_time * 1000),
        })
        return response
    except Exception:
        elapsed = time.perf_counter() - start
        logger.exception("http_request_failed", extra={
            "method": request.method,
            "path": request.url.path,
            "elapsed_ms": int(elapsed * 1000),
        })
        raise
```

### 4. Distributed tracing

In production, instrument with OpenTelemetry to trace requests across services:

```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

jaeger_exporter = JaegerExporter(agent_host_name="localhost", agent_port=6831)
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))

tracer = trace.get_tracer(__name__)

@app.get("/cards")
async def list_cards():
    with tracer.start_as_current_span("get_cards"):
        cards = await cards_service.list()
        return cards
```

---

## Query Optimization

### EXPLAIN ANALYZE

Before running a slow query in production, analyze its execution plan:

```sql
EXPLAIN ANALYZE
SELECT c.id, c.name, p.price
FROM card_catalog.cards c
LEFT JOIN pricing.card_prices p ON c.id = p.card_id
WHERE c.set_code = 'MIR' AND p.price > 10
ORDER BY c.name
LIMIT 20;
```

**Output example:**

```
                                                       QUERY PLAN
─────────────────────────────────────────────────────────────────────────────────
 Limit  (cost=100.50..102.00 rows=20) (actual time=15.234..15.456 rows=20)
   ->  Sort  (cost=100.50..105.50 rows=500) (actual time=15.200..15.300 rows=25)
         Sort Key: c.name
         ->  Hash Left Join  (cost=50.00..80.00 rows=500) (actual time=5.123..10.456 rows=500)
               Hash Cond: (c.id = p.card_id)
               ->  Seq Scan on cards c  (cost=0.00..40.00 rows=1000) (actual time=0.1..2.3 rows=1000)
                     Filter: (set_code = 'MIR')
               ->  Hash  (cost=40.00..40.00 rows=800) (actual time=2.0..2.0 rows=800)
                     ->  Seq Scan on card_prices p  (cost=0.00..40.00 rows=800) (actual time=0.1..1.5 rows=800)
                           Filter: (price > 10)
```

**Key signals:**

- **Seq Scan:** Full table scan (slow on large tables; add an index)
- **Index Scan:** Uses an index (fast)
- **Nested Loop Join:** Slow for large result sets (use Hash Join instead)
- **actual time > cost estimate:** The optimizer guessed wrong (update stats: `ANALYZE cards;`)

### Indexing strategy

**Create indexes for:**

1. **WHERE clauses:** Columns frequently filtered
   ```sql
   CREATE INDEX idx_cards_set_code ON card_catalog.cards(set_code);
   ```

2. **JOIN conditions:** Columns used in ON clauses
   ```sql
   CREATE INDEX idx_prices_card_id ON pricing.card_prices(card_id);
   ```

3. **ORDER BY:** Columns sorted in results
   ```sql
   CREATE INDEX idx_cards_name_set ON card_catalog.cards(set_code, name);
   ```

4. **Composite indexes:** Multiple columns, in order of selectivity
   ```sql
   -- For WHERE set_code = ? AND rarity = ? ORDER BY price
   CREATE INDEX idx_cards_composite ON card_catalog.cards(set_code, rarity, price);
   ```

**Avoid over-indexing:**

- Each index increases INSERT/UPDATE/DELETE cost
- Storage overhead (indexes consume disk space)
- Benchmark before and after: `EXPLAIN ANALYZE` + real query latency

### Partial indexes

Index only rows matching a condition:

```sql
-- Only active cards (cheaper to maintain)
CREATE INDEX idx_cards_active ON card_catalog.cards(name)
WHERE status = 'active';
```

### Statistics maintenance

PostgreSQL's query optimizer uses table statistics. Update them regularly:

```sql
ANALYZE card_catalog.cards;  -- Update stats for one table
ANALYZE;  -- Update stats for all tables
```

**In Docker (daily cron):**

```bash
0 2 * * * docker exec automana-postgres-prod psql -U postgres -d automana -c "ANALYZE;"
```

---

## Caching Strategy

### Redis for session and cache

Redis caches frequently-accessed, read-heavy data. Always cache data that:

1. Takes > 100ms to compute
2. Is accessed > 10 times per minute
3. Changes infrequently (or is invalidated explicitly)

**Example: Cache card listings**

```python
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

async def get_cards_for_set(set_code: str, max_age_seconds: int = 3600) -> list:
    # Try cache
    cache_key = f"cards:set:{set_code}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Cache miss; fetch from DB
    cards = await cards_repository.find_by_set(set_code)
    
    # Store in cache for 1 hour
    redis_client.setex(cache_key, max_age_seconds, json.dumps(cards))
    
    return cards
```

### Cache invalidation

**Problem:** Cached data becomes stale when underlying data changes.

**Solutions:**

1. **Time-based expiration (TTL):** Cache expires after N seconds
   ```python
   redis_client.setex(key, 3600, value)  # Expire after 1 hour
   ```

2. **Event-based invalidation:** Delete cache when data changes
   ```python
   async def update_card_price(card_id: int, new_price: float):
       await prices_repository.update(card_id, new_price)
       redis_client.delete(f"card:price:{card_id}")  # Invalidate
   ```

3. **Cache-aside pattern:** Let cache expire, then update
   ```python
   # No manual invalidation; let TTL handle it
   redis_client.setex(key, 3600, value)  # 1-hour TTL
   ```

### Application-level caching

For data expensive to recompute, cache in-memory:

```python
from functools import lru_cache
from datetime import datetime, timedelta

_cache = {}
_cache_expiry = {}

async def get_expensive_computation(param: str):
    now = datetime.now()
    
    # Check if cached and not expired
    if param in _cache and _cache_expiry.get(param, now) > now:
        return _cache[param]
    
    # Compute
    result = await expensive_operation(param)
    
    # Cache for 5 minutes
    _cache[param] = result
    _cache_expiry[param] = now + timedelta(minutes=5)
    
    return result
```

### Cache warming

Pre-populate cache at startup to avoid initial cache misses:

```python
async def warm_cache():
    logger.info("Warming cache...")
    
    # Cache popular sets
    popular_sets = ["MIR", "DOM", "RTR"]
    for set_code in popular_sets:
        await get_cards_for_set(set_code)
    
    logger.info("Cache warming complete")

@app.on_event("startup")
async def startup():
    await warm_cache()
```

---

## Batch Processing Optimization

### Batch size tuning

Process data in batches (not one record at a time) to amortize overhead:

**Bad (N+1 problem):**

```python
cards = await cards_repository.list(limit=10000)
for card in cards:
    await prices_repository.update(card.id, card.new_price)  # 10k DB calls
```

**Good (batch insert):**

```python
cards = await cards_repository.list(limit=10000)
updates = [(card.id, card.new_price) for card in cards]
await prices_repository.batch_update(updates)  # 1 DB call
```

**Repository implementation:**

```python
async def batch_update(self, updates: list[tuple]) -> int:
    """Update multiple prices in one SQL call."""
    query = """
    UPDATE pricing.card_prices SET price = $2
    WHERE card_id = $1
    """
    
    # Use asyncpg's executemany (much faster than loop)
    rows = await self.pool.executemany(query, updates)
    return len(rows)
```

### Batch size formula

Larger batches reduce I/O overhead, but:
- Larger batches use more memory
- Longer transactions may lock tables

**Rule of thumb:**

```
Batch size = 1000 to 5000 rows for 1-10KB records
Adjust down if memory-constrained or transactions lock frequently
```

**Monitor transaction duration:**

```python
import time

@timer
async def process_batch(batch: list):
    start = time.perf_counter()
    await repository.batch_update(batch)
    elapsed = time.perf_counter() - start
    
    logger.info("Batch update", extra={
        "batch_size": len(batch),
        "duration_ms": int(elapsed * 1000),
        "records_per_second": len(batch) / elapsed,
    })
```

### Connection pooling for batch jobs

Celery tasks process data in parallel. Share a connection pool across workers:

```python
# In Celery worker setup
from automana.core.database import init_async_pool

pool = None

def setup_pool():
    global pool
    loop = asyncio.get_event_loop()
    pool = loop.run_until_complete(init_async_pool(settings))

@shared_task
def process_batch(batch_id: int):
    """Celery task shares the global pool."""
    rows = await pool.fetch("SELECT * FROM batch WHERE id = $1", batch_id)
    # ... process rows
```

---

## Async Efficiency and Concurrency

### async/await patterns

Use async/await to allow other requests to run while waiting for I/O:

```python
# Good: concurrent requests
@app.get("/cards")
async def list_cards():
    # While this request waits for the DB, other requests can run
    cards = await cards_repository.list()
    return cards

# Bad: blocking code prevents other requests
@app.get("/cards")
def list_cards_sync():  # Not async
    # While this request waits, all other requests queue up (single-threaded)
    cards = cards_repository.list()  # Blocking call
    return cards
```

### Celery concurrency

Configure worker concurrency based on CPU and I/O patterns:

**In Docker Compose:**

```yaml
celery-worker:
  command: celery -A automana.worker.app worker -l info --concurrency=4
  # --concurrency=4: Run 4 tasks in parallel
```

**Concurrency guidelines:**

- **CPU-bound work:** `concurrency = number of CPU cores`
- **I/O-bound work (database, HTTP):** `concurrency = 2 × number of CPU cores` (or higher if mostly waiting)
- **Memory-constrained:** Lower concurrency to reduce memory usage

**Verify concurrency:**

```bash
# In Flower, check active tasks and worker stats
curl http://localhost:5555/api/workers
```

### Connection pool sizing

The connection pool must accommodate peak concurrency:

```python
# In src/automana/core/database.py
pool = await asyncpg.create_pool(
    dsn=...,
    min_size=10,      # Minimum connections to keep open
    max_size=20,      # Maximum connections (queue if exceeded)
)
```

**Formula:**

```
max_size >= expected_concurrent_tasks + buffer
```

**Examples:**

- 4 Celery workers, each processing 1 DB query: `max_size = 4 + 5 = 9` (round up to 10)
- FastAPI + Celery: `max_size = (10 HTTP + 4 Celery) + 10 = 24` (round to 30)

**Monitor pool exhaustion:**

```python
logger.info("Pool stats", extra={
    "pool_size": pool.get_size(),
    "pool_idle_size": pool.get_idle_size(),
    "waiting_tasks": len(pool._holders),
})
```

---

## Database Connection Pooling

### asyncpg pool

FastAPI uses `asyncpg` for async database access. The pool manages connections:

```python
import asyncpg

async def init_async_pool(settings):
    pool = await asyncpg.create_pool(
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        host=settings.db_host,
        port=settings.db_port,
        min_size=10,
        max_size=20,
        command_timeout=10,
        max_cached_statement_lifetime=300,
    )
    return pool

@app.get("/cards")
async def list_cards():
    async with app.state.async_db_pool.acquire() as conn:
        cards = await conn.fetch("SELECT * FROM card_catalog.cards LIMIT 100")
    return cards
```

### Connection timeout and retry

Handle connection failures gracefully:

```python
import asyncio

async def init_async_pool_with_retry(settings, max_retries=5):
    for attempt in range(max_retries):
        try:
            pool = await asyncio.wait_for(
                asyncpg.create_pool(...),
                timeout=5.0
            )
            logger.info("Database pool initialized")
            return pool
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                logger.warning(f"Pool init failed; retrying in {wait_time}s", extra={"error": str(e)})
                await asyncio.sleep(wait_time)
            else:
                logger.error("Pool init failed after retries", extra={"error": str(e)})
                raise
```

---

## Monitoring Performance Metrics

### Key metrics to track

| Metric | Target | Alert if > |
|--------|--------|-----------|
| HTTP request latency (p99) | 200ms | 1000ms |
| Database query latency (p99) | 100ms | 500ms |
| Celery task duration (p99) | 30s | 120s |
| Connection pool utilization | 50% | 90% |
| Cache hit rate | 80%+ | < 60% |
| Slow query count | 0 per minute | > 1 per minute |

### Prometheus metrics

Export metrics from FastAPI for Prometheus scraping:

```python
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0)
)

# Database metrics
db_queries_total = Counter(
    'db_queries_total',
    'Total database queries',
    ['operation', 'table']
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['operation', 'table']
)

pool_connections_in_use = Gauge(
    'db_pool_connections_in_use',
    'Active database connections'
)

# Middleware to record metrics
@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    
    http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(elapsed)
    
    return response
```

**Scrape config (Prometheus):**

```yaml
scrape_configs:
  - job_name: 'automana-backend'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

---

## Common Bottlenecks and Solutions

### Problem: Slow bulk uploads

**Symptom:** Importing 100k cards takes 30+ minutes

**Root cause:** N+1 queries (insert one card at a time)

**Solution:** Batch inserts

```python
# Bad: 100k queries
for card in cards:
    await cards_repository.create(card)

# Good: 1 query per 1000 cards
batch_size = 1000
for i in range(0, len(cards), batch_size):
    batch = cards[i:i+batch_size]
    await cards_repository.batch_create(batch)
```

**Result:** 30min → 2min

### Problem: Cache misses on every request

**Symptom:** High database load despite caching

**Root cause:** Cache key is too specific (includes user ID, timestamp, etc.)

**Solution:** Generalize cache keys

```python
# Bad: unique key per user + time
cache_key = f"cards:user:{user_id}:time:{timestamp}"
if user_id == 123 and timestamp changes every second, cache never hits

# Good: generic key per set, indexed by date
cache_key = f"cards:set:{set_code}:date:{date}"
if multiple users request the same set on the same day, cache hits
```

### Problem: Memory leaks in Celery workers

**Symptom:** Worker memory grows to 2GB after 24 hours

**Root cause:** Caching without bounds, large task results retained

**Solution:** Limit cache size or clear cache periodically

```python
from functools import lru_cache

@lru_cache(maxsize=128)  # Limit to 128 cached results
async def expensive_query(param):
    return await db.fetch(...)

# Periodic cache clear
@shared_task
def clear_cache():
    expensive_query.cache_clear()
```

**Or use eviction:**

```python
import redis

redis_client = redis.Redis()
redis_client.setex(key, 3600, value)  # Auto-evict after 1 hour
```

### Problem: Database connection timeout on traffic spike

**Symptom:** Intermittent 504 errors, "connection timeout" in logs

**Root cause:** Pool size too small for concurrent traffic

**Solution:** Increase pool size

```yaml
# Before: max_size=10
pool = await asyncpg.create_pool(..., max_size=10)

# After: max_size=30
pool = await asyncpg.create_pool(..., max_size=30)
```

**Monitor:** Log pool exhaustion

```python
async with pool.acquire() as conn:
    logger.debug("Pool acquired", extra={
        "pool_size": pool.get_size(),
        "pool_idle": pool.get_idle_size(),
    })
```

### Problem: Slow price update pipeline

**Symptom:** MTGStock pipeline takes 2+ hours

**Root cause:** Sequential processing instead of parallel

**Solution:** Increase Celery concurrency

```yaml
celery-worker:
  command: celery -A automana.worker.app worker -l info --concurrency=8
```

---

## Benchmarking Approaches

### Load testing

Use `locust` or `k6` to simulate traffic and measure performance:

```python
# locust: load_test.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def list_cards(self):
        self.client.get("/api/cards")
    
    @task(1)
    def get_card(self):
        self.client.get("/api/cards/123")
```

**Run:**

```bash
locust -f load_test.py -u 100 -r 10 -t 5m http://localhost:8000
```

**Interpretation:**

- RPS (requests per second)
- Response time (p50, p95, p99)
- Error rate

### Profiling production

Use `py-spy` to profile a live process:

```bash
py-spy record -o profile.txt -d 30 -p $(pgrep -f "uvicorn") --function
```

**Flamegraph:**

```bash
py-spy record -o profile.svg -d 30 -p $(pgrep -f "uvicorn")
open profile.svg  # View in browser
```

### Database benchmarking

Compare query performance before and after optimization:

```bash
# Before indexing
time psql -U postgres -d automana -c "EXPLAIN ANALYZE SELECT ..." > before.txt

# Add index
CREATE INDEX idx_cards_set_code ON cards(set_code);
ANALYZE;

# After indexing
time psql -U postgres -d automana -c "EXPLAIN ANALYZE SELECT ..." > after.txt

# Compare
diff before.txt after.txt
```

---

## Summary

AutoMana performance optimization priorities:

1. **Identify bottlenecks** (EXPLAIN ANALYZE, profiling, logs)
2. **Add indexes** on frequently-filtered or joined columns
3. **Batch operations** (inserts, updates) to reduce I/O
4. **Cache aggressively** (Redis for hot data, application-level for expensive queries)
5. **Tune concurrency** (Celery workers, connection pools)
6. **Monitor continuously** (Prometheus metrics, slow query logs)

The fastest query is the one that never executes — cache it. The next fastest is one that executes efficiently — index it and batch it.
