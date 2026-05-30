import base64 as _base64
import json as _json
import redis as redis_lib
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown, worker_ready
from automana.core.framework.service_manager import ServiceManager
from automana.worker.ressources import get_state, init_backend_runtime, shutdown_backend_runtime
from automana.core.log.logging_config import configure_logging
from automana.core.log.logging_context import set_task_id, set_request_id, set_service_path
from automana.worker.celery_metrics import setup_celery_metrics
import inspect, logging


configure_logging()
logger = logging.getLogger(__name__)

from automana.worker.celeryconfig import beat_schedule as _beat_schedule

app = Celery('etl')
app.config_from_object("automana.worker.celeryconfig")
app.conf.timezone = "Australia/Brisbane"
app.conf.enable_utc = False

@worker_process_init.connect
def _init(**_):
    configure_logging()
    setup_celery_metrics()
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
                 , retry_kwargs={"max_retries": 0}
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
    # DEBUG: per-step executor wiring — fires once per chain link, not a
    # business event. Keep at DEBUG so the default INFO level stays quiet
    # across multi-step pipelines (e.g. the 10-step scryfall chain or the
    # 3 inner execute_service calls inside run_alert_check).
    logger.debug(
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


def _build_beat_fingerprints() -> set:
    fps: set = set()
    for entry in _beat_schedule.values():
        task = entry["task"]
        if task == "run_service":
            path = entry.get("kwargs", {}).get("path")
            if path:
                fps.add(("run_service", path))
        else:
            fps.add((task,))
    return fps


def _task_fingerprint(raw: bytes):
    try:
        msg = _json.loads(raw)
        task_name = msg.get("headers", {}).get("task")
        if not task_name:
            return None
        if task_name == "run_service":
            body = _json.loads(_base64.b64decode(msg["body"]))
            kwargs = body[1] if isinstance(body, list) and len(body) > 1 else {}
            path = kwargs.get("path") if isinstance(kwargs, dict) else None
            return ("run_service", path) if path else None
        return (task_name,)
    except Exception:
        return None


@worker_ready.connect
def _purge_stale_beat_tasks(sender, **_):
    beat_fingerprints = _build_beat_fingerprints()
    r = redis_lib.from_url(sender.app.conf.broker_url)
    raw_items = r.lrange("celery", 0, -1)

    groups: dict = {}
    for raw in raw_items:
        fp = _task_fingerprint(raw)
        if fp and fp in beat_fingerprints:
            groups.setdefault(fp, []).append(raw)

    purged: dict = {}
    for fp, items in groups.items():
        if len(items) > 1:
            for duplicate in items[1:]:
                r.lrem("celery", 1, duplicate)
            label = fp[1] if fp[0] == "run_service" else fp[0].split(".")[-1]
            purged[label] = len(items) - 1

    if purged:
        logger.warning("Stale beat tasks purged on startup", extra={"purged": purged})