import logging
from datetime import datetime, timedelta, timezone
from automana.core.service_registry import ServiceRegistry
from automana.core.metrics.buffer import MetricsBuffer
from automana.core.repositories.metrics_repositories.metrics_repository import MetricsRepository
from automana.core.settings import get_settings

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "ops.metrics.flush_hourly_metrics",
    db_repositories=["metrics"]
)
async def flush_hourly_metrics(metrics_repository: MetricsRepository) -> dict:
    """Flush in-memory metrics buffer to database."""
    buffer = MetricsBuffer.get_instance()
    api_buf, celery_buf = buffer.flush()

    metrics_to_insert = []

    # Process API metrics
    for (hour_key, endpoint, status_code), bucket in api_buf.items():
        hour_timestamp = datetime.fromtimestamp(hour_key * 3600, tz=timezone.utc)
        agg = bucket.aggregate()

        metrics_to_insert.append({
            'hour': hour_timestamp,
            'metric_type': 'api_request',
            'endpoint': endpoint,
            'task_name': None,
            'status_code': status_code,
            'request_count': agg['request_count'],
            'error_count': agg['error_count'],
            'cache_hit_count': agg['cache_hit_count'],
            'response_time_p95': agg.get('response_time_p95'),
            'response_time_median': agg.get('response_time_median'),
            'response_time_max': agg.get('response_time_max'),
            'celery_success_count': None,
            'celery_failure_count': None,
            'error_rate': agg['error_rate'],
            'cache_hit_rate': agg['cache_hit_rate'],
            'celery_success_rate': None,
        })

    # Process Celery metrics
    for (hour_key, task_name), bucket in celery_buf.items():
        hour_timestamp = datetime.fromtimestamp(hour_key * 3600, tz=timezone.utc)
        agg = bucket.aggregate()

        metrics_to_insert.append({
            'hour': hour_timestamp,
            'metric_type': 'celery_task',
            'endpoint': None,
            'task_name': task_name,
            'status_code': None,
            'request_count': 0,
            'error_count': 0,
            'cache_hit_count': 0,
            'response_time_p95': None,
            'response_time_median': None,
            'response_time_max': None,
            'celery_success_count': agg['success_count'],
            'celery_failure_count': agg['failure_count'],
            'error_rate': None,
            'cache_hit_rate': None,
            'celery_success_rate': agg['success_rate'],
        })

    if metrics_to_insert:
        count = await metrics_repository.insert_hourly_metrics(metrics_to_insert)
        logger.info("Flushed hourly metrics", extra={
            "rows_inserted": count,
            "api_buckets": len(api_buf),
            "celery_buckets": len(celery_buf)
        })
        return {
            "rows_inserted": count,
            "api_buckets": len(api_buf),
            "celery_buckets": len(celery_buf)
        }

    logger.info("No metrics to flush")
    return {"rows_inserted": 0}


@ServiceRegistry.register(
    "ops.metrics.discord_weekly_report",
    db_repositories=["metrics"]
)
async def discord_weekly_report(metrics_repository: MetricsRepository) -> dict:
    """Generate and post weekly metrics report to Discord."""
    settings = get_settings()
    if not settings.metrics.DISCORD_WEBHOOK_URL:
        logger.warning("Discord webhook URL not configured, skipping report")
        return {"status": "skipped", "reason": "no_webhook_url"}

    # Calculate week boundaries (Mon 00:00 - Sun 23:59)
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    start_dt = datetime.combine(monday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(sunday, datetime.max.time()).replace(tzinfo=timezone.utc)

    # Fetch metrics
    api_metrics = await metrics_repository.get_weekly_api_metrics(start_dt, end_dt)
    celery_metrics = await metrics_repository.get_weekly_celery_metrics(start_dt, end_dt)

    if not api_metrics and not celery_metrics:
        message = "📊 Weekly Metrics\n\nNo metrics recorded this week."
        await _post_to_discord(settings.metrics.DISCORD_WEBHOOK_URL, message)
        return {"status": "posted", "message": "no_data"}

    # Build message
    message = "📊 Weekly Metrics (Mon–Sun)\n\n"

    # API endpoints table
    if api_metrics:
        message += "**API Endpoints**\n"
        message += "| Endpoint | Hits | P95 (ms) | Error Rate | Cache Hit |\n"
        message += "|----------|------|----------|-----------|----------|\n"

        by_endpoint = {}
        for row in api_metrics:
            endpoint = row['endpoint'] or "unknown"
            if endpoint not in by_endpoint:
                by_endpoint[endpoint] = {
                    'request_count': 0,
                    'response_time_p95': [],
                    'error_rate': [],
                    'cache_hit_rate': []
                }
            by_endpoint[endpoint]['request_count'] += row['request_count'] or 0
            if row['response_time_p95']:
                by_endpoint[endpoint]['response_time_p95'].append(row['response_time_p95'])
            if row['error_rate'] is not None:
                by_endpoint[endpoint]['error_rate'].append(row['error_rate'])
            if row['cache_hit_rate'] is not None:
                by_endpoint[endpoint]['cache_hit_rate'].append(row['cache_hit_rate'])

        for endpoint in sorted(by_endpoint.keys(), key=lambda k: by_endpoint[k]['request_count'], reverse=True)[:10]:
            stats = by_endpoint[endpoint]
            hits = stats['request_count']
            p95 = max(stats['response_time_p95']) if stats['response_time_p95'] else 0
            err_rate = sum(stats['error_rate']) / len(stats['error_rate']) if stats['error_rate'] else 0
            cache_rate = sum(stats['cache_hit_rate']) / len(stats['cache_hit_rate']) if stats['cache_hit_rate'] else 0

            message += f"| {endpoint} | {hits} | {p95:.0f} | {err_rate*100:.1f}% | {cache_rate*100:.0f}% |\n"
        message += "\n"

    # Celery tasks table
    if celery_metrics:
        message += "**Celery Tasks**\n"
        message += "| Task | Median (ms) | Max (ms) | Success Rate |\n"
        message += "|------|-------------|---------|----------|\n"

        by_task = {}
        for row in celery_metrics:
            task = row['task_name'] or "unknown"
            if task not in by_task:
                by_task[task] = {
                    'execution_times': [],
                    'success_rate': []
                }
            if row['response_time_median']:
                by_task[task]['execution_times'].append(row['response_time_median'])
            if row['response_time_max']:
                by_task[task]['execution_times'].append(row['response_time_max'])
            if row['celery_success_rate'] is not None:
                by_task[task]['success_rate'].append(row['celery_success_rate'])

        for task in sorted(by_task.keys()):
            stats = by_task[task]
            if stats['execution_times']:
                median = sorted(stats['execution_times'])[len(stats['execution_times'])//2]
                max_time = max(stats['execution_times'])
            else:
                median = 0
                max_time = 0
            success = sum(stats['success_rate']) / len(stats['success_rate']) if stats['success_rate'] else 0

            message += f"| {task} | {median:.0f} | {max_time:.0f} | {success*100:.1f}% |\n"

    await _post_to_discord(settings.metrics.DISCORD_WEBHOOK_URL, message)
    logger.info("Posted weekly metrics report to Discord")
    return {"status": "posted"}


@ServiceRegistry.register(
    "ops.metrics.cleanup_old_metrics",
    db_repositories=["metrics"]
)
async def cleanup_old_metrics(metrics_repository: MetricsRepository) -> dict:
    """Delete metrics older than the retention window."""
    settings = get_settings()
    retention_days = settings.metrics.METRICS_RETENTION_DAYS
    rows_deleted = await metrics_repository.delete_metrics_older_than(retention_days)

    logger.info("Cleaned up old metrics", extra={
        "retention_days": retention_days,
        "rows_deleted": rows_deleted
    })
    return {
        "rows_deleted": rows_deleted,
        "retention_days": retention_days
    }


async def _post_to_discord(webhook_url: str, message: str) -> None:
    """Post a message to Discord webhook."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        payload = {"content": message}
        async with session.post(webhook_url, json=payload) as resp:
            if resp.status not in (200, 204):
                logger.error("Failed to post to Discord", extra={"status": resp.status})
