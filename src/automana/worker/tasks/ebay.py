"""Dedicated Celery tasks for eBay sold-price persistence.

Sync and scrape use dedicated tasks (not run_service) because they iterate
all active sellers internally; promote uses run_service.
"""
import logging

import automana.core.services.app_integration.ebay.category_sweep_service  # noqa: F401
import automana.core.services.app_integration.ebay.refresh_scrape_targets_service  # noqa: F401
import automana.core.services.app_integration.ebay.scrape_global_market_service  # noqa: F401

from automana.worker.main import app
from automana.worker.ressources import get_state, init_backend_runtime
from automana.core.framework.service_manager import ServiceManager
from automana.core.log.logging_context import set_task_id, set_service_path

logger = logging.getLogger(__name__)


@app.task(
    name="automana.worker.tasks.ebay.ebay_sync_own_sales_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_sync_own_sales_task(self, days_back: int = 90):
    state = get_state()
    set_task_id(self.request.id)
    set_service_path("integrations.ebay.sync_own_sales")
    if not state.initialized:
        init_backend_runtime()
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(
                "integrations.ebay.sync_own_sales",
                days_back=days_back,
            )
        )
        logger.info(
            "ebay_sync_own_sales_task_complete",
            extra={"result": result},
        )
        return result
    except Exception:
        logger.exception("ebay_sync_own_sales_task_failed")
        raise
    finally:
        set_service_path(None)
        set_task_id(None)


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
    state = get_state()
    set_task_id(self.request.id)
    set_service_path("integrations.ebay.scrape_external_sold")
    if not state.initialized:
        init_backend_runtime()
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service(
                "integrations.ebay.scrape_external_sold",
                days_back=days_back,
                score_threshold=score_threshold,
                limit_per_card=limit_per_card,
            )
        )
        logger.info(
            "ebay_scrape_external_sold_task_complete",
            extra={"result": result},
        )
        return result
    except Exception:
        logger.exception("ebay_scrape_external_sold_task_failed")
        raise
    finally:
        set_service_path(None)
        set_task_id(None)


@app.task(
    name="automana.worker.tasks.ebay.ebay_category_sweep_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_category_sweep_task(self):
    """Daily category-wide eBay sold sweep across EBAY-US, EBAY-AU, EBAY-ENCA."""
    state = get_state()
    set_task_id(self.request.id)
    set_service_path("integrations.ebay.category_sweep")
    if not state.initialized:
        init_backend_runtime()
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service("integrations.ebay.category_sweep")
        )
        logger.info("ebay_category_sweep_task_complete", extra={"result": result})
        return result
    except Exception:
        logger.exception("ebay_category_sweep_task_failed")
        raise
    finally:
        set_service_path(None)
        set_task_id(None)
