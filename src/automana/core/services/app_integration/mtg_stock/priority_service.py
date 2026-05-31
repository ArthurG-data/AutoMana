import logging

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.mtg_stock.priority_repository import (
    MtgstockPriorityRepository,
)

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "mtg_stock.priority.get_tier_print_ids",
    db_repositories=["mtg_stock_priority"],
)
async def get_tier_print_ids(
    mtg_stock_priority_repository: MtgstockPriorityRepository,
    tier: int,
) -> dict:
    """Return {"print_ids": [...]} for the given tier."""
    print_ids = await mtg_stock_priority_repository.fetch_tier_print_ids(tier)
    logger.info("MTGStock tier print_ids computed", extra={"tier": tier, "count": len(print_ids)})
    return {"print_ids": print_ids}
