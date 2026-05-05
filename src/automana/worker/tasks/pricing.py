from celery import shared_task
import logging
from datetime import datetime, date, timedelta
from automana.worker.main import run_service
from automana.core.logging_context import set_task_id

logger = logging.getLogger(__name__)


@shared_task(name="refresh_daily_prices", bind=True)
def refresh_daily_prices_task(self):
    """
    Daily task to refresh Tier 2 (print_price_daily) from Tier 1 (price_observation).

    Links source_product_id → card_version_id via mtg_card_products table.
    Runs daily to populate the aggregated daily prices for charts and analytics.
    """
    set_task_id(self.request.id)
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    logger.info(
        "Starting pricing tier 2 refresh (daily aggregates)",
        extra={"date": yesterday.isoformat()},
    )

    try:
        result = run_service(
            "pricing.refresh_daily_prices",
            p_from=yesterday,
            p_to=yesterday,
        )
        logger.info(
            "Pricing tier 2 refresh completed",
            extra={"result": result, "date": yesterday.isoformat()},
        )
        return {"status": "success", "date": yesterday.isoformat()}
    except Exception as e:
        logger.error(
            "Pricing tier 2 refresh failed",
            extra={"error": str(e), "date": yesterday.isoformat()},
        )
        raise


@shared_task(name="archive_to_weekly_prices", bind=True)
def archive_to_weekly_prices_task(self):
    """
    Monthly task to archive Tier 2 (daily) to Tier 3 (weekly rollups).

    Runs monthly to move data older than 5 years to the weekly archive.
    Reduces storage and speeds up Tier 2 queries by archiving old data.
    """
    set_task_id(self.request.id)
    logger.info(
        "Starting pricing tier 3 archive (weekly rollups)",
        extra={"older_than": "5 YEARS"},
    )

    try:
        result = run_service(
            "pricing.archive_to_weekly",
            older_than_interval="5 YEARS",
        )
        logger.info(
            "Pricing tier 3 archive completed",
            extra={"result": result},
        )
        return {"status": "success"}
    except Exception as e:
        logger.error(
            "Pricing tier 3 archive failed",
            extra={"error": str(e)},
        )
        raise
