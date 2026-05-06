import time
import pytest
from unittest.mock import MagicMock
from automana.worker.celery_metrics import setup_celery_metrics, on_task_prerun, on_task_success
from automana.core.metrics.buffer import MetricsBuffer


@pytest.fixture
def clear_buffer():
    MetricsBuffer.get_instance().clear()
    yield
    MetricsBuffer.get_instance().clear()


def test_celery_task_success_signal(clear_buffer):
    """Task success signal should record execution time."""
    setup_celery_metrics()  # Register signal handlers
    buffer = MetricsBuffer.get_instance()

    # Simulate task_prerun signal
    task_id = "test-task-123"
    from automana.worker.celery_metrics import _task_times

    sender = MagicMock()
    on_task_prerun(sender=sender, task_id=task_id)
    assert task_id in _task_times

    # Simulate some work time
    time.sleep(0.01)

    # Simulate task_success signal
    sender = MagicMock()
    sender.name = "test.task"

    on_task_success(sender=sender, task_id=task_id)

    # Verify buffer recorded the metric
    _, celery_buf = buffer.flush()
    assert len(celery_buf) > 0
