"""Refresh the ebay_scrape_targets watchlist from rare/mythic/promo cards above a value threshold."""
from __future__ import annotations

import logging
from typing import Any

from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_MIN_CENTS = 100   # $1.00 USD


@ServiceRegistry.register(
    path="integrations.ebay.refresh_scrape_targets",
    db_repositories=["ebay_scrape"],
    runs_in_transaction=False,
)
async def refresh_scrape_targets(
    ebay_scrape_repository: EbayScrapeSoldRepository,
    **kwargs: Any,
) -> dict:
    """Upsert rare/mythic/promo cards with sell_avg_cents >= threshold into ebay_scrape_targets."""
    settings = get_settings()
    min_cents = getattr(settings, "ebay_scrape_target_min_cents", _DEFAULT_MIN_CENTS)

    await ebay_scrape_repository.deactivate_stale_targets(min_cents=min_cents)
    await ebay_scrape_repository.refresh_scrape_targets(min_cents=min_cents)
    logger.info("ebay_refresh_scrape_targets_complete", extra={"min_cents": min_cents})
    return {"status": "ok", "min_cents": min_cents}
