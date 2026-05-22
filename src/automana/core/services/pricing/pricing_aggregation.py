from datetime import date
from typing import Optional
import logging

from automana.core.repositories.pricing.price_repository import PricingTierRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "pricing.refresh_daily_prices",
    db_repositories=["pricing"],
    runs_in_transaction=False,
)
async def refresh_daily_prices(
    pricing_repository: PricingTierRepository,
    p_from: Optional[date] = None,
    p_to: Optional[date] = None,
) -> dict:
    """
    Service to refresh Tier 2 (daily aggregates) from Tier 1 (raw observations).

    Links source_product_id → card_version_id via mtg_card_products table.
    Populates print_price_daily and print_price_latest.

    Args:
        pricing_repository: PricingTierRepository instance (injected as "pricing")
        p_from: Start date. If None, uses watermark.
        p_to: End date. If None, uses yesterday.

    Returns:
        Dict with status and counts.
    """
    if isinstance(p_from, str):
        p_from = date.fromisoformat(p_from)
    if isinstance(p_to, str):
        p_to = date.fromisoformat(p_to)
    return await pricing_repository.refresh_daily_prices(p_from=p_from, p_to=p_to)


@ServiceRegistry.register(
    "pricing.archive_to_weekly",
    db_repositories=["pricing"],
)
async def archive_to_weekly(
    pricing_repository: PricingTierRepository,
    older_than_interval: str = "5 YEARS",
) -> dict:
    """
    Service to archive Tier 2 (daily) to Tier 3 (weekly rollups).

    Args:
        pricing_repository: PricingTierRepository instance (injected as "pricing")
        older_than_interval: PostgreSQL interval (e.g., '5 YEARS')

    Returns:
        Dict with status and counts.
    """
    return await pricing_repository.archive_to_weekly(
        older_than_interval=older_than_interval
    )


@ServiceRegistry.register(
    "pricing.mv_card_price_spark.refresh",
    db_repositories=["pricing"],
    runs_in_transaction=False,
    # REFRESH MATERIALIZED VIEW CONCURRENTLY on print_price_daily (365-day window,
    # ~10k card versions) routinely exceeds the pool's 60s default. 3600s matches
    # the ceiling used by other daily aggregation services in this module.
    command_timeout=3600,
)
async def refresh_card_price_spark(
    pricing_repository: PricingTierRepository,
    **kwargs,
) -> dict:
    return await pricing_repository.refresh_card_price_spark()
