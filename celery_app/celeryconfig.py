broker_url='redis://localhost:6379/0'
result_backend='redis://localhost:6379/1'

imports = (
    'celery_app.tasks.scryfall',
    'celery_app.tasks.app_authentification',
    'celery_app.tasks.ebay',
    )

timezone = "Australia/Brisbane"
from celery.schedules import crontab
beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "tasks.scryfall.download_scryfall_bulk_uris",
        "schedule": crontab(hour=2, minute=0, day_of_week='sun'),  # 02:00 AEST
    },
}