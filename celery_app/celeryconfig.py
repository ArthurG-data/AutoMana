import os
from pathlib import Path
from dotenv import load_dotenv
from celery.schedules import crontab

broker_url=os.getenv("BROKER_URL")
result_backend=os.getenv("RESULT_BACKEND")

imports = (
    'celery_app.tasks.pipelines',
    #'celery_app.tasks.app_authentification',
    #'celery_app.tasks.ebay',
    )

timezone = os.getenv("CELERY_TIMEZONE", "Australia/Sydney")

beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "tasks.daily_scryfall_data_pipeline",
        "schedule": crontab(hour=2, minute=0),  # 02:00 AEST
    },
}
