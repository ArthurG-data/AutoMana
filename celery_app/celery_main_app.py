import logging
from celery import Celery

celery_app = Celery('etl')
celery_app.config_from_object('celery_app.celeryconfig')

try:
    celery_app.connection().ensure_connection(max_retries=3)
    logging.info("Connected to the message broker successfully.")
except Exception as e:
    logging.error(f"Failed to connect to the message broker: {e}")

@celery_app.task
def hello():
    return "Hello, World!"
