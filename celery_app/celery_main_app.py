import os, logging
from celery import Celery
from dotenv import load_dotenv



celery_app = Celery('etl')
celery_app.config_from_object('celeryconfig')

@celery_app.task
def hello():
    return "Hello, World!"
