import pytest
from automana.core.metrics.buffer import MetricsBuffer


def test_metrics_buffer_singleton():
    """MetricsBuffer should return the same instance."""
    buffer1 = MetricsBuffer.get_instance()
    buffer2 = MetricsBuffer.get_instance()
    assert buffer1 is buffer2


def test_metrics_buffer_add_api_metric():
    buffer = MetricsBuffer.get_instance()
    buffer.clear()

    buffer.add_api_metric(
        hour_key=1,
        endpoint="/api/test",
        status_code=200,
        elapsed=0.05,
        is_error=False,
        is_cache_hit=True,
    )

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
