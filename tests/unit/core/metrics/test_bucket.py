import pytest
from automana.core.metrics.bucket import MetricBucket, CeleryMetricBucket


def test_metric_bucket_add_request():
    """Test adding individual requests."""
    bucket = MetricBucket()
    bucket.add(0.100, is_error=False, is_cache_hit=False)
    bucket.add(0.150, is_error=False, is_cache_hit=True)
    bucket.add(0.200, is_error=True, is_cache_hit=False)

    assert bucket.request_count == 3
    assert bucket.error_count == 1
    assert bucket.cache_hit_count == 1
    assert len(bucket.response_times) == 3


def test_metric_bucket_aggregate():
    """Test aggregation with 100 requests."""
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
    """Test recording Celery task metrics."""
    bucket = CeleryMetricBucket()
    bucket.add_success(1.5)
    bucket.add_success(1.2)
    bucket.add_failure(2.0)

    assert bucket.success_count == 2
    assert bucket.failure_count == 1
    assert len(bucket.execution_times) == 3


def test_celery_metric_bucket_aggregate():
    """Test Celery aggregation with 10 tasks."""
    bucket = CeleryMetricBucket()
    for i in range(10):
        if i % 3 == 0:
            bucket.add_failure(1.0 + i * 0.1)
        else:
            bucket.add_success(1.0 + i * 0.1)

    stats = bucket.aggregate()
    assert stats['success_count'] == 6
    assert stats['failure_count'] == 4
    assert stats['success_rate'] == pytest.approx(6/10)
    assert 'median_execution_time' in stats
    assert 'max_execution_time' in stats
