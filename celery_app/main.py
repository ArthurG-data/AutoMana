from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from celery_app.ressources import init_db_pool, shutdown_db_pool

celery_app = Celery('etl')
celery_app.config_from_object("celery_app.celeryconfig")

@worker_process_init.connect
def _init(**_):
    init_db_pool()

@worker_process_shutdown.connect
def _shutdown(**_):
    shutdown_db_pool()

@celery_app.task
def hello():
    return "Hello, World!"
