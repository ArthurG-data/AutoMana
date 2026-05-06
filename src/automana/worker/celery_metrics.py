import time
import logging
from celery.signals import task_prerun, task_success, task_failure
from automana.core.metrics.buffer import MetricsBuffer

logger = logging.getLogger(__name__)

# Module-level variables
_task_times = {}  # Dict[task_id, start_time_float]
_buffer = MetricsBuffer.get_instance()


def on_task_prerun(sender=None, task_id=None, **kwargs):
    """Record task start time when task begins execution.

    Args:
        sender: The task instance.
        task_id: The unique task ID.
        **kwargs: Additional signal arguments.
    """
    _task_times[task_id] = time.time()


def on_task_success(sender=None, task_id=None, **kwargs):
    """Record successful task execution metrics.

    Args:
        sender: The task instance.
        task_id: The unique task ID.
        **kwargs: Additional signal arguments.
    """
    # Check if task_id in _task_times
    if task_id not in _task_times:
        logger.warning("task_id not found in _task_times", extra={"task_id": task_id})
        return

    try:
        # Calculate elapsed time
        elapsed = time.time() - _task_times[task_id]

        # Get hour key and task name
        hour_key = int(time.time() // 3600)
        task_name = sender.name if sender else "unknown"

        # Record metric in buffer
        _buffer.add_celery_metric(hour_key=hour_key, task_name=task_name, elapsed=elapsed, is_success=True)
    except Exception as exc:
        logger.error("error recording celery success metric", extra={"task_id": task_id, "error": str(exc)})
    finally:
        # Clean up task_times
        _task_times.pop(task_id, None)


def on_task_failure(sender=None, task_id=None, **kwargs):
    """Record failed task execution metrics.

    Args:
        sender: The task instance.
        task_id: The unique task ID.
        **kwargs: Additional signal arguments.
    """
    # Check if task_id in _task_times
    if task_id not in _task_times:
        logger.warning("task_id not found in _task_times", extra={"task_id": task_id})
        return

    try:
        # Calculate elapsed time
        elapsed = time.time() - _task_times[task_id]

        # Get hour key and task name
        hour_key = int(time.time() // 3600)
        task_name = sender.name if sender else "unknown"

        # Record metric in buffer
        _buffer.add_celery_metric(hour_key=hour_key, task_name=task_name, elapsed=elapsed, is_success=False)
    except Exception as exc:
        logger.error("error recording celery failure metric", extra={"task_id": task_id, "error": str(exc)})
    finally:
        # Clean up task_times
        _task_times.pop(task_id, None)


def setup_celery_metrics():
    """Register Celery signal handlers at worker startup.

    This function should be called once during Celery worker initialization
    to register handlers for task lifecycle signals.
    """
    task_prerun.connect(on_task_prerun, weak=False)
    task_success.connect(on_task_success, weak=False)
    task_failure.connect(on_task_failure, weak=False)
    logger.info("Celery metrics signal handlers registered")
