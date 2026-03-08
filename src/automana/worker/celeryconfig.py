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


_default_redis_host = "redis" if _running_in_container() else "localhost"

broker_url = os.getenv("BROKER_URL", f"redis://{_default_redis_host}:6379/0")
result_backend = os.getenv("RESULT_BACKEND", f"redis://{_default_redis_host}:6379/1")


imports = {
    "automana.worker.tasks.pipelines",
    "automana.worker.tasks.analytics",
}


worker_prefetch_multiplier = 1

timezone = os.getenv("CELERY_TIMEZONE", "Australia/Sydney")

beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "automana.worker.tasks.pipelines.daily_scryfall_data_pipeline",
        "schedule": crontab(hour=8, minute=8),  # 02:00 AEST
    },
        "refresh-mtgjson-daily": {
            "task": "automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline",
            "schedule": crontab(hour=9, minute=8),  # 03:00 AEST
        },
    "daily-analytics-report": {
        "task": "automana.worker.tasks.analytics.daily_summary_analytics_task",
        "schedule": crontab(hour=11, minute=0),  # 03:00 AEST
    }
}


