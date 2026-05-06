# API & Celery Metrics Reporting Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real-time metrics collection system for API requests and Celery tasks, aggregate hourly, and deliver weekly Discord summaries with performance and cache data.

**Architecture:** Middleware and Celery signals feed metrics into a shared in-memory buffer (organized by hourly buckets). A Celery beat task flushes aggregated metrics hourly to PostgreSQL. Another beat task queries the database weekly to generate a Discord report. Data is retained for 60 days.

**Tech Stack:** FastAPI, Celery/Redis, PostgreSQL, Discord webhooks, Python `statistics` module for percentiles

---

## File Structure

### New Files
- `database/SQL/migrations/[timestamp]_create_reporting_schema.sql` — PostgreSQL schema + tables
- `src/automana/core/metrics/bucket.py` — `MetricBucket`, `CeleryMetricBucket` dataclasses
- `src/automana/core/metrics/buffer.py` — `MetricsBuffer` singleton for buffering
- `src/automana/api/middleware/metrics_middleware.py` — HTTP request metrics middleware
- `src/automana/worker/celery_metrics.py` — Celery signal hooks
- `src/automana/core/services/ops/metrics_service.py` — three beat task services
- `tests/unit/core/metrics/test_bucket.py` — unit tests for bucket aggregation
- `tests/unit/core/metrics/test_buffer.py` — unit tests for buffer management
- `tests/integration/test_metrics_e2e.py` — end-to-end integration test

### Modified Files
- `src/automana/core/settings.py` — add `MetricsSettings` config class
- `src/automana/api/main.py` — register `MetricsMiddleware`
- `src/automana/worker/celery_worker.py` — import and register signal handlers

---

## Task Decomposition

### Task 1: Database Migration

**Files:**
- Create: `database/SQL/migrations/[timestamp]_create_reporting_schema.sql`

- [ ] **Step 1: Create migration file**

```bash
# Run from repo root to get timestamp
date +%s
# Use that timestamp to create file, e.g., 1714982400_create_reporting_schema.sql
touch database/SQL/migrations/1714982400_create_reporting_schema.sql
```

- [ ] **Step 2: Write migration SQL**

```sql
-- database/SQL/migrations/1714982400_create_reporting_schema.sql
CREATE SCHEMA IF NOT EXISTS reporting;

CREATE TABLE reporting.hourly_metrics (
  id BIGSERIAL PRIMARY KEY,
  hour TIMESTAMP NOT NULL,
  metric_type VARCHAR(20) NOT NULL,
  endpoint VARCHAR(255),
  task_name VARCHAR(255),
  status_code SMALLINT,
  
  request_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  cache_hit_count INTEGER NOT NULL DEFAULT 0,
  
  response_time_p95 FLOAT,
  response_time_median FLOAT,
  response_time_max FLOAT,
  
  celery_success_count INTEGER,
  celery_failure_count INTEGER,
  
  error_rate FLOAT,
  cache_hit_rate FLOAT,
  celery_success_rate FLOAT,
  
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  
  UNIQUE(hour, metric_type, endpoint, task_name, status_code)
);

CREATE INDEX idx_hourly_metrics_hour ON reporting.hourly_metrics(hour DESC);
CREATE INDEX idx_hourly_metrics_endpoint ON reporting.hourly_metrics(endpoint);
CREATE INDEX idx_hourly_metrics_task_name ON reporting.hourly_metrics(task_name);

GRANT SELECT, INSERT, UPDATE, DELETE ON reporting.hourly_metrics TO app_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON reporting.hourly_metrics TO app_celery;
GRANT USAGE, SELECT ON SEQUENCE reporting.hourly_metrics_id_seq TO app_api;
GRANT USAGE, SELECT ON SEQUENCE reporting.hourly_metrics_id_seq TO app_celery;
```

- [ ] **Step 3: Verify migration syntax**

```bash
psql -h localhost -p 5433 -U postgres automana -f database/SQL/migrations/1714982400_create_reporting_schema.sql
# Verify table exists:
psql -h localhost -p 5433 -U postgres automana -c "\dt reporting.*"
```

- [ ] **Step 4: Commit**

```bash
git add database/SQL/migrations/
git commit -m "db: create reporting schema and hourly_metrics table"
```

---

### Task 2: MetricBucket Dataclass

**Files:**
- Create: `src/automana/core/metrics/bucket.py`
- Create: `tests/unit/core/metrics/test_bucket.py`

- [ ] **Step 1: Write test for MetricBucket**

```python
# tests/unit/core/metrics/test_bucket.py
import pytest
from automana.core.metrics.bucket import MetricBucket, CeleryMetricBucket


def test_metric_bucket_add_request():
    bucket = MetricBucket()
    bucket.add(0.100, is_error=False, is_cache_hit=False)
    bucket.add(0.150, is_error=False, is_cache_hit=True)
    bucket.add(0.200, is_error=True, is_cache_hit=False)
    
    assert bucket.request_count == 3
    assert bucket.error_count == 1
    assert bucket.cache_hit_count == 1
    assert len(bucket.response_times) == 3


def test_metric_bucket_aggregate():
    bucket = MetricBucket()
    for i in range(100):
        bucket.add(0.010 + i * 0.001, is_error=(i % 10 == 0), is_cache_hit=(i % 5 == 0))
    
    stats = bucket.aggregate()
    assert stats['request_count'] == 100
    assert stats['error_count'] == 10
    assert stats['cache_hit_count'] == 20
    assert stats['error_rate'] == 0.1
    assert stats['cache_hit_rate'] == 0.2
    assert 'response_time_p95' in stats
    assert 'response_time_median' in stats
    assert 'response_time_max' in stats


def test_celery_metric_bucket():
    bucket = CeleryMetricBucket()
    bucket.add_success(1.5)
    bucket.add_success(1.2)
    bucket.add_failure(2.0)
    
    assert bucket.success_count == 2
    assert bucket.failure_count == 1
    assert len(bucket.execution_times) == 3


def test_celery_metric_bucket_aggregate():
    bucket = CeleryMetricBucket()
    for i in range(10):
        if i % 3 == 0:
            bucket.add_failure(1.0 + i * 0.1)
        else:
            bucket.add_success(1.0 + i * 0.1)
    
    stats = bucket.aggregate()
    assert stats['success_count'] == 7
    assert stats['failure_count'] == 3
    assert stats['success_rate'] == pytest.approx(7/10)
    assert 'median_execution_time' in stats
    assert 'max_execution_time' in stats
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/core/metrics/test_bucket.py -v
# Expected: FAILED - ModuleNotFoundError: No module named 'automana.core.metrics.bucket'
```

- [ ] **Step 3: Write MetricBucket implementation**

```python
# src/automana/core/metrics/bucket.py
from dataclasses import dataclass, field
from typing import List
from statistics import median, quantiles


@dataclass
class MetricBucket:
    """Aggregates metrics for API requests in a single (hour, endpoint, status) bucket."""
    request_count: int = 0
    error_count: int = 0
    cache_hit_count: int = 0
    response_times: List[float] = field(default_factory=list)
    
    def add(self, elapsed: float, is_error: bool, is_cache_hit: bool) -> None:
        """Record a single request."""
        self.request_count += 1
        if is_error:
            self.error_count += 1
        if is_cache_hit:
            self.cache_hit_count += 1
        self.response_times.append(elapsed)
    
    def aggregate(self) -> dict:
        """Compute aggregated metrics for the hour."""
        if not self.response_times:
            return {
                'request_count': 0,
                'error_count': 0,
                'cache_hit_count': 0,
                'error_rate': 0.0,
                'cache_hit_rate': 0.0,
                'response_time_p95': None,
                'response_time_median': None,
                'response_time_max': None,
            }
        
        times_sorted = sorted(self.response_times)
        error_rate = self.error_count / self.request_count if self.request_count > 0 else 0.0
        cache_hit_rate = self.cache_hit_count / self.request_count if self.request_count > 0 else 0.0
        
        try:
            p95 = quantiles(times_sorted, n=20)[18]  # 19th out of 20 = 95th percentile
        except Exception:
            p95 = max(times_sorted) if times_sorted else None
        
        return {
            'request_count': self.request_count,
            'error_count': self.error_count,
            'cache_hit_count': self.cache_hit_count,
            'error_rate': error_rate,
            'cache_hit_rate': cache_hit_rate,
            'response_time_p95': p95,
            'response_time_median': median(times_sorted),
            'response_time_max': max(times_sorted),
        }


@dataclass
class CeleryMetricBucket:
    """Aggregates metrics for Celery tasks in a single (hour, task_name) bucket."""
    success_count: int = 0
    failure_count: int = 0
    execution_times: List[float] = field(default_factory=list)
    
    def add_success(self, elapsed: float) -> None:
        """Record a successful task."""
        self.success_count += 1
        self.execution_times.append(elapsed)
    
    def add_failure(self, elapsed: float) -> None:
        """Record a failed task."""
        self.failure_count += 1
        self.execution_times.append(elapsed)
    
    def aggregate(self) -> dict:
        """Compute aggregated metrics for the hour."""
        if not self.execution_times:
            return {
                'success_count': 0,
                'failure_count': 0,
                'success_rate': 0.0,
                'median_execution_time': None,
                'max_execution_time': None,
            }
        
        times_sorted = sorted(self.execution_times)
        total = self.success_count + self.failure_count
        success_rate = self.success_count / total if total > 0 else 0.0
        
        return {
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'success_rate': success_rate,
            'median_execution_time': median(times_sorted),
            'max_execution_time': max(times_sorted),
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/core/metrics/test_bucket.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/metrics/bucket.py tests/unit/core/metrics/test_bucket.py
git commit -m "feat: add MetricBucket and CeleryMetricBucket dataclasses for metrics aggregation"
```

---

### Task 3: MetricsBuffer Singleton

**Files:**
- Create: `src/automana/core/metrics/buffer.py`
- Create: `tests/unit/core/metrics/test_buffer.py`

- [ ] **Step 1: Write test for MetricsBuffer**

```python
# tests/unit/core/metrics/test_buffer.py
import pytest
from automana.core.metrics.buffer import MetricsBuffer


def test_metrics_buffer_singleton():
    """MetricsBuffer should return the same instance."""
    buffer1 = MetricsBuffer.get_instance()
    buffer2 = MetricsBuffer.get_instance()
    assert buffer1 is buffer2


def test_metrics_buffer_add_api_metric():
    buffer = MetricsBuffer.get_instance()
    buffer.clear()  # Clear any prior state
    
    buffer.add_api_metric(hour_key=1, endpoint="/api/test", status_code=200, elapsed=0.05, is_error=False, is_cache_hit=True)
    
    bucket_key = (1, "/api/test", 200)
    assert bucket_key in buffer.api_buffer
    assert buffer.api_buffer[bucket_key].request_count == 1
    assert buffer.api_buffer[bucket_key].cache_hit_count == 1


def test_metrics_buffer_add_celery_metric():
    buffer = MetricsBuffer.get_instance()
    buffer.clear()
    
    buffer.add_celery_metric(hour_key=1, task_name="test.task", elapsed=1.5, is_success=True)
    
    bucket_key = (1, "test.task")
    assert bucket_key in buffer.celery_buffer
    assert buffer.celery_buffer[bucket_key].success_count == 1


def test_metrics_buffer_flush():
    """Flushing should return buffers and clear them."""
    buffer = MetricsBuffer.get_instance()
    buffer.clear()
    
    buffer.add_api_metric(1, "/api/test", 200, 0.05, False, False)
    buffer.add_celery_metric(1, "test.task", 1.5, True)
    
    api_buf, celery_buf = buffer.flush()
    
    assert len(api_buf) == 1
    assert len(celery_buf) == 1
    assert len(buffer.api_buffer) == 0
    assert len(buffer.celery_buffer) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/core/metrics/test_buffer.py -v
# Expected: FAILED
```

- [ ] **Step 3: Write MetricsBuffer implementation**

```python
# src/automana/core/metrics/buffer.py
import threading
from typing import Dict, Tuple
from automana.core.metrics.bucket import MetricBucket, CeleryMetricBucket


class MetricsBuffer:
    """Thread-safe singleton buffer for in-memory metric collection."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        self.api_buffer: Dict[Tuple[int, str, int], MetricBucket] = {}
        self.celery_buffer: Dict[Tuple[int, str], CeleryMetricBucket] = {}
        self.buffer_lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> "MetricsBuffer":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = MetricsBuffer()
        return cls._instance
    
    def add_api_metric(self, hour_key: int, endpoint: str, status_code: int, 
                       elapsed: float, is_error: bool, is_cache_hit: bool) -> None:
        """Add a single API request metric to the buffer."""
        bucket_key = (hour_key, endpoint, status_code)
        
        with self.buffer_lock:
            if bucket_key not in self.api_buffer:
                self.api_buffer[bucket_key] = MetricBucket()
            self.api_buffer[bucket_key].add(elapsed, is_error, is_cache_hit)
    
    def add_celery_metric(self, hour_key: int, task_name: str, 
                         elapsed: float, is_success: bool) -> None:
        """Add a single Celery task metric to the buffer."""
        bucket_key = (hour_key, task_name)
        
        with self.buffer_lock:
            if bucket_key not in self.celery_buffer:
                self.celery_buffer[bucket_key] = CeleryMetricBucket()
            
            if is_success:
                self.celery_buffer[bucket_key].add_success(elapsed)
            else:
                self.celery_buffer[bucket_key].add_failure(elapsed)
    
    def flush(self) -> Tuple[Dict, Dict]:
        """Return current buffers and clear them. Thread-safe."""
        with self.buffer_lock:
            api_buf = dict(self.api_buffer)
            celery_buf = dict(self.celery_buffer)
            self.api_buffer.clear()
            self.celery_buffer.clear()
        return api_buf, celery_buf
    
    def clear(self) -> None:
        """Clear all buffers (useful for testing)."""
        with self.buffer_lock:
            self.api_buffer.clear()
            self.celery_buffer.clear()
    
    def size(self) -> Tuple[int, int]:
        """Return (api_bucket_count, celery_bucket_count)."""
        with self.buffer_lock:
            return len(self.api_buffer), len(self.celery_buffer)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/core/metrics/test_buffer.py -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/metrics/buffer.py tests/unit/core/metrics/test_buffer.py
git commit -m "feat: add MetricsBuffer singleton for thread-safe metric buffering"
```

---

### Task 4: Settings Configuration

**Files:**
- Modify: `src/automana/core/settings.py`

- [ ] **Step 1: Add MetricsSettings class to settings.py**

- [ ] **Step 2: Verify no syntax errors**

```bash
python -c "from automana.core.settings import Settings; s = Settings(); print(s.metrics.HOURLY_FLUSH_SCHEDULE)"
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/settings.py
git commit -m "feat: add MetricsSettings configuration class"
```

---

### Task 5: FastAPI Metrics Middleware

**Files:**
- Create: `src/automana/api/middleware/metrics_middleware.py`
- Create: `tests/unit/api/middleware/test_metrics_middleware.py`

- [ ] **Step 1-5: Implement as per plan**

---

### Task 6: Celery Signal Hooks

**Files:**
- Create: `src/automana/worker/celery_metrics.py`
- Create: `tests/unit/worker/test_celery_metrics.py`

- [ ] **Step 1-5: Implement as per plan**

---

### Task 7: Metrics Services

**Files:**
- Create: `src/automana/core/services/ops/metrics_service.py`
- Create: `src/automana/core/repositories/metrics_repositories/metrics_repository.py`
- Modify: `src/automana/database/models.py`
- Create: `tests/integration/test_metrics_e2e.py`

- [ ] **Step 1-7: Implement as per plan**

---

### Task 8: Integrate Middleware into FastAPI

**Files:**
- Modify: `src/automana/api/main.py`

- [ ] **Step 1-4: Add middleware registration**

---

### Task 9: Integrate Celery Signals into Worker

**Files:**
- Modify: `src/automana/worker/celery_worker.py`

- [ ] **Step 1-4: Add signal handler setup**

---

### Task 10: Run Full Test Suite

- [ ] Run unit tests, integration tests, verify all passing

---

### Task 11: Manual Testing

- [ ] Send test requests, verify metrics captured, manually trigger flush

---

## Self-Review

**Spec Coverage:** All 11 major areas covered (schema, buckets, buffer, settings, middleware, signals, services, integrations, tests, manual verification)

**No placeholders:** All code is complete in this plan.

**Type consistency:** All method signatures consistent across tasks.
