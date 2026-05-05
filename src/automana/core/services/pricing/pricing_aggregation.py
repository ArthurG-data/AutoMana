from datetime import date
from typing import Optional
import logging

from automana.core.repositories.pricing.price_repository import PricingTierRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "pricing.refresh_daily_prices",
    db_repositories=["pricing"],
)
async def refresh_daily_prices(
    price_repository: PricingTierRepository,
    p_from: Optional[date] = None,
    p_to: Optional[date] = None,
) -> dict:
    """
    Service to refresh Tier 2 (daily aggregates) from Tier 1 (raw observations).

    Links source_product_id → card_version_id via mtg_card_products table.
    Populates print_price_daily and print_price_latest.

    Args:
        price_repository: PriceRepository instance
        p_from: Start date. If None, uses watermark.
        p_to: End date. If None, uses yesterday.

    Returns:
        Dict with status and counts.
    """
    return await price_repository.refresh_daily_prices(p_from=p_from, p_to=p_to)


@ServiceRegistry.register(
    "pricing.archive_to_weekly",
    db_repositories=["pricing"],
)
async def archive_to_weekly(
    price_repository: PricingTierRepository,
    older_than_interval: str = "5 YEARS",
) -> dict:
    """
    Service to archive Tier 2 (daily) to Tier 3 (weekly rollups).

    Args:
        price_repository: PriceRepository instance
        older_than_interval: PostgreSQL interval (e.g., '5 YEARS')

    Returns:
        Dict with status and counts.
    """
    return await price_repository.archive_to_weekly(
        older_than_interval=older_than_interval
    )
