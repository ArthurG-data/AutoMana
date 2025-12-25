from celery import Celery

celery_app = Celery('etl')
celery_app.config_from_object('celeryconfig')

@celery_app.task
def hello():
    return "Hello, World!"
