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

@celery_app.task(name="run_service"
                 , bind=True
                 , autoretry_for=(Exception,)
                 , retry_kwargs={"max_retries": 3}
                 , retry_backoff=True
                 , acks_late=True)
def run_service(self, path: str, **kwargs):
    state = get_state()
    if not state.initialized:
        init_backend_runtime()
    self.update_state(state="STARTED", meta={"service": path, "attempt": self.request.retries + 1})
    try:
        result = state.async_runner.run(ServiceManager.execute_service(path, **kwargs))
        self.update_state(state="SUCCESS", meta={"service": path, "result": result})
        return result
    except Exception as e:
        self.update_state(state="FAILURE", meta={"service": path, "exc": str(e)})
        raise