"""Sealed product pricing service steps.

Registered steps:
  pricing.sealed.bootstrap_catalog  — upsert sealed product catalog
  pricing.sealed.get_prices_by_set  — query current prices for a set
  pricing.sealed.get_price_history  — query price history for one product
"""
from __future__ import annotations

import logging
from datetime import date

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.pricing.sealed_pricing_repository import SealedPricingRepository

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "pricing.sealed.bootstrap_catalog",
    db_repositories=["sealed_pricing"],
)
async def bootstrap_sealed_catalog(
    sealed_pricing_repository: SealedPricingRepository,
    sealed_products_data: list[dict],
) -> dict:
    """Upsert sealed product catalog rows.

    Each element of ``sealed_products_data`` must contain:
      mtgjson_uuid, name, product_type, set_code
    """
    count = await sealed_pricing_repository.upsert_sealed_products(sealed_products_data)
    logger.info("Sealed catalog bootstrapped", extra={"catalog_upserted": count})
    return {"catalog_upserted": count}


@ServiceRegistry.register(
    "pricing.sealed.get_prices_by_set",
    db_repositories=["sealed_pricing"],
)
async def get_sealed_prices_by_set(
    sealed_pricing_repository: SealedPricingRepository,
    set_code: str,
) -> list[dict]:
    """Return current sealed product prices for all products in a set."""
    return await sealed_pricing_repository.get_sealed_prices_by_set(set_code)


@ServiceRegistry.register(
    "pricing.sealed.get_price_history",
    db_repositories=["sealed_pricing"],
)
async def get_sealed_price_history(
    sealed_pricing_repository: SealedPricingRepository,
    mtgjson_uuid: str,
    from_date: date,
    to_date: date,
) -> list[dict]:
    """Return price history for a single sealed product over a date range."""
    return await sealed_pricing_repository.get_sealed_price_history(
        mtgjson_uuid, from_date, to_date
    )
