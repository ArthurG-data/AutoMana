from dataclasses import dataclass, field
from statistics import median, quantiles, StatisticsError


@dataclass
class MetricBucket:
    """Aggregates API request metrics."""

    request_count: int = 0
    error_count: int = 0
    cache_hit_count: int = 0
    response_times: list = field(default_factory=list)

    def add(self, elapsed: float, is_error: bool, is_cache_hit: bool) -> None:
        """Record a single request metric.

        Args:
            elapsed: Response time in seconds
            is_error: Whether the request resulted in an error
            is_cache_hit: Whether the response came from cache
        """
        self.request_count += 1
        if is_error:
            self.error_count += 1
        if is_cache_hit:
            self.cache_hit_count += 1
        self.response_times.append(elapsed)

    def aggregate(self) -> dict:
        """Compute aggregated statistics.

        Returns:
            Dictionary with request_count, error_count, cache_hit_count,
            error_rate, cache_hit_rate, response_time_p95, response_time_median,
            and response_time_max.
        """
        stats = {
            'request_count': self.request_count,
            'error_count': self.error_count,
            'cache_hit_count': self.cache_hit_count,
        }

        if self.request_count > 0:
            stats['error_rate'] = self.error_count / self.request_count
            stats['cache_hit_rate'] = self.cache_hit_count / self.request_count
        else:
            stats['error_rate'] = 0.0
            stats['cache_hit_rate'] = 0.0

        if self.response_times:
            stats['response_time_median'] = median(self.response_times)
            stats['response_time_max'] = max(self.response_times)

            try:
                # quantiles with n=20 gives 19 cut points, the 95th percentile is at index 18
                p95 = quantiles(self.response_times, n=20)[18]
                stats['response_time_p95'] = p95
            except (StatisticsError, IndexError):
                # If quantiles fails (too few samples), use max as fallback
                stats['response_time_p95'] = max(self.response_times)
        else:
            stats['response_time_median'] = None
            stats['response_time_max'] = None
            stats['response_time_p95'] = None

        return stats


@dataclass
class CeleryMetricBucket:
    """Aggregates Celery task metrics."""

    success_count: int = 0
    failure_count: int = 0
    execution_times: list = field(default_factory=list)

    def add_success(self, elapsed: float) -> None:
        """Record a successful task execution.

        Args:
            elapsed: Execution time in seconds
        """
        self.success_count += 1
        self.execution_times.append(elapsed)

    def add_failure(self, elapsed: float) -> None:
        """Record a failed task execution.

        Args:
            elapsed: Execution time in seconds
        """
        self.failure_count += 1
        self.execution_times.append(elapsed)

    def aggregate(self) -> dict:
        """Compute aggregated statistics.

        Returns:
            Dictionary with success_count, failure_count, success_rate,
            median_execution_time, and max_execution_time.
        """
        total_tasks = self.success_count + self.failure_count
        stats = {
            'success_count': self.success_count,
            'failure_count': self.failure_count,
        }

        if total_tasks > 0:
            stats['success_rate'] = self.success_count / total_tasks
        else:
            stats['success_rate'] = 0.0

        if self.execution_times:
            stats['median_execution_time'] = median(self.execution_times)
            stats['max_execution_time'] = max(self.execution_times)
        else:
            stats['median_execution_time'] = None
            stats['max_execution_time'] = None

        return stats
