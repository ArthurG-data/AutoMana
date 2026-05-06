import logging
from datetime import datetime, timedelta
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)


class MetricsRepository(AbstractRepository):
    """Repository for managing hourly metrics in the reporting schema."""

    @property
    def name(self) -> str:
        return "MetricsRepository"

    async def insert_hourly_metrics(self, metrics_data: list) -> int:
        """Bulk insert hourly metrics. Returns count inserted.

        Args:
            metrics_data: List of dictionaries with metric fields

        Returns:
            Number of rows inserted
        """
        if not metrics_data:
            return 0

        query = """
        INSERT INTO reporting.hourly_metrics (
            hour,
            metric_type,
            endpoint,
            task_name,
            status_code,
            request_count,
            error_count,
            cache_hit_count,
            response_time_p95,
            response_time_median,
            response_time_max,
            celery_success_count,
            celery_failure_count,
            error_rate,
            cache_hit_rate,
            celery_success_rate
        ) VALUES """

        params = []
        placeholders = []
        param_idx = 1

        for metric in metrics_data:
            placeholders.append(f"""
                (${param_idx}, ${param_idx + 1}, ${param_idx + 2}, ${param_idx + 3}, ${param_idx + 4},
                 ${param_idx + 5}, ${param_idx + 6}, ${param_idx + 7}, ${param_idx + 8}, ${param_idx + 9},
                 ${param_idx + 10}, ${param_idx + 11}, ${param_idx + 12}, ${param_idx + 13}, ${param_idx + 14},
                 ${param_idx + 15})
            """)
            params.extend([
                metric['hour'],
                metric['metric_type'],
                metric.get('endpoint'),
                metric.get('task_name'),
                metric.get('status_code'),
                metric.get('request_count', 0),
                metric.get('error_count', 0),
                metric.get('cache_hit_count', 0),
                metric.get('response_time_p95'),
                metric.get('response_time_median'),
                metric.get('response_time_max'),
                metric.get('celery_success_count'),
                metric.get('celery_failure_count'),
                metric.get('error_rate'),
                metric.get('cache_hit_rate'),
                metric.get('celery_success_rate'),
            ])
            param_idx += 16

        query += ",".join(placeholders) + " ON CONFLICT (hour, metric_type, endpoint, task_name, status_code) DO NOTHING"

        await self.execute_command(query, *params)
        return len(metrics_data)

    async def get_weekly_api_metrics(self, start_date: datetime, end_date: datetime) -> list:
        """Fetch API metrics for a date range.

        Args:
            start_date: Start of the date range
            end_date: End of the date range

        Returns:
            List of metric rows
        """
        query = """
        SELECT
            id, hour, metric_type, endpoint, task_name, status_code,
            request_count, error_count, cache_hit_count,
            response_time_p95, response_time_median, response_time_max,
            celery_success_count, celery_failure_count,
            error_rate, cache_hit_rate, celery_success_rate,
            created_at
        FROM reporting.hourly_metrics
        WHERE metric_type = 'api_request'
          AND hour >= $1
          AND hour <= $2
        ORDER BY request_count DESC
        """
        rows = await self.execute_query(query, start_date, end_date)
        return rows

    async def get_weekly_celery_metrics(self, start_date: datetime, end_date: datetime) -> list:
        """Fetch Celery metrics for a date range.

        Args:
            start_date: Start of the date range
            end_date: End of the date range

        Returns:
            List of metric rows
        """
        query = """
        SELECT
            id, hour, metric_type, endpoint, task_name, status_code,
            request_count, error_count, cache_hit_count,
            response_time_p95, response_time_median, response_time_max,
            celery_success_count, celery_failure_count,
            error_rate, cache_hit_rate, celery_success_rate,
            created_at
        FROM reporting.hourly_metrics
        WHERE metric_type = 'celery_task'
          AND hour >= $1
          AND hour <= $2
        """
        rows = await self.execute_query(query, start_date, end_date)
        return rows

    async def delete_metrics_older_than(self, days: int) -> int:
        """Delete metrics older than N days. Returns count deleted.

        Args:
            days: Number of days of retention

        Returns:
            Number of rows deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = """
        DELETE FROM reporting.hourly_metrics
        WHERE created_at < $1
        """
        result = await self.execute_command(query, cutoff)
        return result if isinstance(result, int) else 0

    # Abstract methods required by AbstractRepository
    async def add(self, item) -> None:
        raise NotImplementedError("Use insert_hourly_metrics instead")

    async def get(self, id: int):
        raise NotImplementedError("Use get_weekly_* methods instead")

    async def update(self, item) -> None:
        raise NotImplementedError("Metrics are write-once")

    async def delete(self, id: int) -> None:
        raise NotImplementedError("Use delete_metrics_older_than instead")

    async def list(self, items) -> list:
        raise NotImplementedError("Use get_weekly_* methods instead")
