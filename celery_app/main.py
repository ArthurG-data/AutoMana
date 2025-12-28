from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from backend.core.service_manager import ServiceManager
from celery_app.ressources import get_state, init_backend_runtime, shutdown_backend_runtime

celery_app = Celery('etl')
celery_app.config_from_object("celery_app.celeryconfig")

@worker_process_init.connect
def _init(**_):
    init_backend_runtime()

@worker_process_shutdown.connect
def _shutdown(**_):
    shutdown_backend_runtime()


@celery_app.task(name="ping")
def ping():
    return "pong"

@celery_app.task(name="run_service")
def run_service(path: str, **kwargs):
    state = get_state()
    if not state.initialized:
        init_backend_runtime()

    # execute_service is async; async_runner.run expects a coroutine
    return state.async_runner.run(ServiceManager.execute_service(path, **kwargs))