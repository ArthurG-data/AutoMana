"""Dedicated Celery tasks for eBay sold-price persistence.

Sync and scrape use dedicated tasks (not run_service) because they iterate
all active sellers internally; promote uses run_service.
"""
import logging

import automana.core.services.app_integration.ebay.category_sweep_service  # noqa: F401
import automana.core.services.app_integration.ebay.refresh_scrape_targets_service  # noqa: F401
import automana.core.services.app_integration.ebay.sales_sync_service  # noqa: F401
import automana.core.services.app_integration.ebay.scrape_global_market_service  # noqa: F401
from automana.core.services.app_integration.ebay.ebay_raw_io import get_ebay_raw_dir

from automana.worker.main import app
from automana.worker.ressources import get_state, init_backend_runtime
from automana.core.framework.service_manager import ServiceManager
from automana.core.log.logging_context import set_task_id, set_service_path

logger = logging.getLogger(__name__)


def _run_ebay_service(task_self, service_path: str, log_key: str, **kwargs):
    """Run a ServiceManager service synchronously inside a Celery task."""
    state = get_state()
    set_task_id(task_self.request.id)
    set_service_path(service_path)
    if not state.initialized:
        init_backend_runtime()
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(service_path, **kwargs)
        )
        logger.info(f"{log_key}_complete", extra={"result": result})
        return result
    except Exception:
        logger.exception(f"{log_key}_failed")
        raise
    finally:
        set_service_path(None)
        set_task_id(None)


@app.task(
    name="automana.worker.tasks.ebay.ebay_sync_own_sales_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_sync_own_sales_task(self, days_back: int = 90):
    return _run_ebay_service(
        self,
        "integrations.ebay.sync_own_sales",
        "ebay_sync_own_sales_task",
        days_back=days_back,
    )


@app.task(
    name="automana.worker.tasks.ebay.ebay_scrape_external_sold_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_scrape_external_sold_task(
    self,
    days_back: int = 30,
    score_threshold: float = 0.7,
    limit_per_card: int = 50,
):
    return _run_ebay_service(
        self,
        "integrations.ebay.scrape_external_sold",
        "ebay_scrape_external_sold_task",
        days_back=days_back,
        score_threshold=score_threshold,
        limit_per_card=limit_per_card,
    )


@app.task(
    name="automana.worker.tasks.ebay.ebay_category_sweep_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_category_sweep_task(self):
    """Daily category-wide eBay sold sweep across EBAY-US, EBAY-AU, EBAY-ENCA."""
    return _run_ebay_service(
        self,
        "integrations.ebay.category_sweep",
        "ebay_category_sweep_task",
    )


def _cleanup_old_ebay_raw_files(max_age_days: int = 7) -> int:
    """Delete JSON files under the ebay_raw directory older than max_age_days. Returns count deleted."""
    import time
    raw_dir = get_ebay_raw_dir()
    if not raw_dir.exists():
        return 0
    cutoff = time.time() - (max_age_days * 86_400)
    deleted = 0
    for f in raw_dir.rglob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            deleted += 1
    return deleted


@app.task(
    name="automana.worker.tasks.ebay.ebay_cleanup_raw_files_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_cleanup_raw_files_task(self):
    """Weekly maintenance: delete eBay raw JSON files older than 7 days."""
    deleted = _cleanup_old_ebay_raw_files(max_age_days=7)
    logger.info("ebay_cleanup_raw_files_complete", extra={"deleted": deleted})
    return {"deleted": deleted}
