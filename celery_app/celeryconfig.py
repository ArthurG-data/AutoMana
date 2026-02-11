import os
from celery.schedules import crontab

broker_url=os.getenv("BROKER_URL")
result_backend=os.getenv("RESULT_BACKEND")


imports = {
    "celery_app.tasks.pipelines",
    "celery_app.tasks.analytics",
}


worker_prefetch_multiplier = 1

timezone = os.getenv("CELERY_TIMEZONE", "Australia/Sydney")

beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "celery_app.tasks.pipelines.daily_scryfall_data_pipeline",
        "schedule": crontab(hour=8, minute=8),  # 02:00 AEST
    },
        "refresh-mtgjson-daily": {
            "task": "celery_app.tasks.pipelines.daily_mtgjson_data_pipeline",
            "schedule": crontab(hour=9, minute=8),  # 03:00 AEST
        },
    "daily-analytics-report": {
        "task": "celery_app.tasks.analytics.daily_summary_analytics_task",
        "schedule": crontab(hour=11, minute=0),  # 03:00 AEST
    }
}


