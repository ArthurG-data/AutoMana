from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from backend.core.service_manager import ServiceManager
from celery_app.ressources import get_state, init_backend_runtime, shutdown_backend_runtime
import inspect

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
def run_service(self,prev=None, path: str = None, **kwargs):
    state = get_state()
    if not state.initialized:
        init_backend_runtime()

    if path is None and isinstance(prev, str):
        path, prev = prev, None

    context = {}
    if isinstance(prev, dict):
        context.update(prev)

    context.update(kwargs)

    if isinstance(prev, dict):
        kwargs = {**prev, **kwargs}

    service_func = ServiceManager.get_service_function(path)
    sig = inspect.signature(service_func)
    allowed_keys = set(sig.parameters.keys())

    filtered_context = {k: v for k, v in context.items() if k in allowed_keys}
    print(f"Running service: {path} kwargs_keys={list(filtered_context.keys())}")
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(path, **filtered_context)
        )

        # 🔑 CRITICAL: merge result back into context
        if isinstance(result, dict):
            context.update(result)

        return context

    except Exception as e:
        print(f"Exception in run_service ({path}): {e}")
        raise