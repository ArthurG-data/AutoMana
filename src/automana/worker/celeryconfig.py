import os
from celery.schedules import crontab
from dotenv import load_dotenv
from automana.core.settings import env_file_path
from urllib.parse import urlsplit, urlunsplit

# Load the same env file strategy used by the backend app.
_env_file = env_file_path()
if _env_file:
    load_dotenv(_env_file, override=False)


def _running_in_container() -> bool:
    return os.path.exists("/.dockerenv") or bool(os.getenv("KUBERNETES_SERVICE_HOST"))


def _fix_redis_host(url: str) -> str:
    """Replace the 'redis' service-name hostname with 'localhost' when not in a container.

    .env.dev hard-codes ``redis://redis:6379/…`` for Docker use.  When Celery
    runs on the host (TUI, manual invocation) that hostname is unresolvable, so
    swap it out here rather than requiring a separate env file.
    """
    if _running_in_container():
        return url
    parts = urlsplit(url)
    if parts.hostname == "redis":
        fixed_netloc = parts.netloc.replace("redis:", "localhost:", 1)
        return urlunsplit(parts._replace(netloc=fixed_netloc))
    return url


_default_redis_host = "redis" if _running_in_container() else "localhost"

broker_url = _fix_redis_host(os.getenv("BROKER_URL", f"redis://{_default_redis_host}:6379/0"))
result_backend = _fix_redis_host(os.getenv("RESULT_BACKEND", f"redis://{_default_redis_host}:6379/1"))


imports = {
    "automana.worker.tasks.pipelines",
    "automana.worker.tasks.analytics",
}


worker_prefetch_multiplier = 1
task_always_eager = False
task_store_eager_result = True

timezone = os.getenv("CELERY_TIMEZONE", "Australia/Sydney")

beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "automana.worker.tasks.pipelines.daily_scryfall_data_pipeline",
        "schedule": crontab(hour=2, minute=0),  # 02:00 AEST
    },
    "refresh-mtgjson-daily": {
        "task": "automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline",
        "schedule": crontab(hour=3, minute=0),  # 03:00 AEST
    },
    # MTGStock staging runs AFTER Scryfall so reject resolver sees fresh
    # scryfall_id migrations, and AFTER MTGJson to avoid contention on the
    # pricing schema.
    "refresh-mtgstock-daily": {
        "task": "automana.worker.tasks.pipelines.mtgStock_download_pipeline",
        "schedule": crontab(hour=4, minute=0),  # 04:00 AEST
    },
    "daily-analytics-report": {
        "task": "automana.worker.tasks.analytics.daily_summary_analytics_task",
        "schedule": crontab(hour=5, minute=0),  # 05:00 AEST — after all data pipelines
    },
    "pipeline-health-am": {
        "task": "automana.worker.tasks.pipelines.pipeline_health_alert_task",
        "schedule": crontab(hour=6, minute=0),  # 06:00 AEST — post-pipeline check
    },
    "pipeline-health-pm": {
        "task": "automana.worker.tasks.pipelines.pipeline_health_alert_task",
        "schedule": crontab(hour=18, minute=0),  # 18:00 AEST — same-day insurance
    },
}


