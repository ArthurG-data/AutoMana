from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from automana.core.service_manager import ServiceManager
from automana.worker.ressources import get_state, init_backend_runtime, shutdown_backend_runtime
from automana.core.logging_config import configure_logging
from automana.core.logging_context import set_task_id, set_request_id, set_service_path
import inspect, logging


configure_logging()
logger = logging.getLogger(__name__)

app = Celery('etl')
app.config_from_object("automana.worker.celeryconfig")
app.conf.timezone = "Australia/Brisbane"
app.conf.enable_utc = False

@worker_process_init.connect
def _init(**_):
    configure_logging()
    init_backend_runtime()

@worker_process_shutdown.connect
def _shutdown(**_):
    shutdown_backend_runtime()


@app.task(name="ping")
def ping():
    return "pong"

@app.task(name="run_service"
                 , bind=True
                 , autoretry_for=(Exception,)
                 , retry_kwargs={"max_retries": 3}
                 , retry_backoff=True
                 , acks_late=True)
def run_service(self,prev=None, path: str = None, **kwargs):
    state = get_state()
    set_task_id(self.request.id)
    if path:
        set_service_path(path)

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
    logger.info(
    "run_service_start",
    extra={"service_path": path, "kwargs_keys": list(filtered_context.keys())}
)
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(path, **filtered_context)
        )

        # 🔑 CRITICAL: merge result back into context
        if isinstance(result, dict):
            context.update(result)

        return context

    except Exception:
        logger.exception("run_service_failed", extra={"service_path": path})
        raise
    finally:
        set_service_path(None)
        set_request_id(None)
        set_task_id(None)