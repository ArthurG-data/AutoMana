import threading
from typing import Dict, Tuple

from automana.core.metrics.bucket import CeleryMetricBucket, MetricBucket


class MetricsBuffer:
    """Thread-safe singleton for buffering API and Celery metrics."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize the buffer with empty dictionaries."""
        self.api_buffer: Dict[Tuple[int, str, int], MetricBucket] = {}
        self.celery_buffer: Dict[Tuple[int, str], CeleryMetricBucket] = {}
        self.buffer_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "MetricsBuffer":
        """Get the singleton instance using double-checked locking pattern.

        Returns:
            The MetricsBuffer singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def add_api_metric(
        self, hour_key: int, endpoint: str, status_code: int, elapsed: float, is_error: bool, is_cache_hit: bool
    ) -> None:
        """Add an API request metric to the buffer.

        Args:
            hour_key: The hour key for bucketing
            endpoint: The API endpoint path
            status_code: The HTTP status code
            elapsed: Response time in seconds
            is_error: Whether the request resulted in an error
            is_cache_hit: Whether the response came from cache
        """
        bucket_key = (hour_key, endpoint, status_code)
        with self.buffer_lock:
            if bucket_key not in self.api_buffer:
                self.api_buffer[bucket_key] = MetricBucket()
            self.api_buffer[bucket_key].add(elapsed, is_error, is_cache_hit)

    def add_celery_metric(self, hour_key: int, task_name: str, elapsed: float, is_success: bool) -> None:
        """Add a Celery task metric to the buffer.

        Args:
            hour_key: The hour key for bucketing
            task_name: The Celery task name
            elapsed: Execution time in seconds
            is_success: Whether the task succeeded
        """
        bucket_key = (hour_key, task_name)
        with self.buffer_lock:
            if bucket_key not in self.celery_buffer:
                self.celery_buffer[bucket_key] = CeleryMetricBucket()
            if is_success:
                self.celery_buffer[bucket_key].add_success(elapsed)
            else:
                self.celery_buffer[bucket_key].add_failure(elapsed)

    def flush(self) -> Tuple[Dict[Tuple[int, str, int], MetricBucket], Dict[Tuple[int, str], CeleryMetricBucket]]:
        """Flush and return copies of the buffers, then clear them.

        Returns:
            A tuple of (api_buffer_copy, celery_buffer_copy) containing the current state,
            and clears both buffers for the next collection period.
        """
        with self.buffer_lock:
            api_buf = dict(self.api_buffer)
            celery_buf = dict(self.celery_buffer)
            self.api_buffer.clear()
            self.celery_buffer.clear()
            return api_buf, celery_buf

    def clear(self) -> None:
        """Clear all buffers (for testing)."""
        with self.buffer_lock:
            self.api_buffer.clear()
            self.celery_buffer.clear()

    def size(self) -> Tuple[int, int]:
        """Get the current size of both buffers.

        Returns:
            A tuple of (api_bucket_count, celery_bucket_count)
        """
        with self.buffer_lock:
            return len(self.api_buffer), len(self.celery_buffer)
