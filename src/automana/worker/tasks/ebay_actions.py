"""Celery task for draining the listing_pending_actions queue."""
import logging

from automana.worker.main import app
from automana.worker.ressources import get_state, init_backend_runtime
from automana.core.framework.service_manager import ServiceManager
from automana.core.log.logging_context import set_task_id, set_service_path

logger = logging.getLogger(__name__)


@app.task(
    name="automana.worker.tasks.ebay_actions.drain_listing_actions_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def drain_listing_actions_task(self, limit: int = 50):
    state = get_state()
    set_task_id(self.request.id)
    set_service_path("integrations.ebay.actions.drain")
    if not state.initialized:
        init_backend_runtime()
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(
                "integrations.ebay.actions.drain",
                limit=limit,
            )
        )
        logger.info(
            "drain_listing_actions_complete",
            extra={"processed": result.get("processed", 0), "failed": result.get("failed", 0)},
        )
        return result
    except Exception:
        logger.exception("drain_listing_actions_failed")
        raise
    finally:
        set_service_path(None)
        set_task_id(None)