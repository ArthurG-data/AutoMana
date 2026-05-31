"""Step 5 — Stage matched PriceCharting sold listings into pricing.ebay_scraped_sold.

Reads the persistent match map (pricing.pricecharting_card_map, the single source
of truth) to resolve each scraped product to a card_version + finish, resolves a
source_product_id per matched card_version, and inserts each accepted sale into
the shared staging table that ``promote_sold_obs`` aggregates into
pricing.price_observation.

Idempotent: the staging item_id is a deterministic hash, so re-running on the
same scraped data inserts nothing new (insert_scraped_sold is ON CONFLICT
(item_id) DO NOTHING).
"""
from __future__ import annotations

import logging
from typing import Any

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.repositories.app_integration.pricecharting.pc_map_repository import (
    PricechartingMapRepository,
)
from automana.core.repositories.pricing.price_repository import PricingTierRepository
from automana.core.services.app_integration.pricecharting import pc_staging
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)

_SOURCE_CODE = "pricecharting"


@ServiceRegistry.register(
    path="pricecharting.stage_sold",
    db_repositories=["pricing", "ebay_scrape", "pricecharting_map"],
    storage_services=["pricecharting"],
)
async def stage_sold(
    pricing_repository: PricingTierRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    pricecharting_map_repository: PricechartingMapRepository,
    storage_service: StorageService,
    **kwargs: Any,
) -> dict:
    """Stage all matched PriceCharting sold listings into pricing.ebay_scraped_sold.

    Requires build_match_catalog (the match map) and scrape_sales (sales/*.json).
    """
    if not await storage_service.file_exists("sets.json"):
        logger.warning("pricecharting_stage_no_sets_file")
        return {"accepted": 0, "inserted": 0, "sets": 0, "source_products": 0}

    catalog = await pricecharting_map_repository.fetch_matched_map()
    if not catalog:
        logger.warning("pricecharting_stage_empty_map")
        return {"accepted": 0, "inserted": 0, "sets": 0, "source_products": 0}

    pc_sets = (await storage_service.load_json("sets.json")).get("sets", [])

    # Ensure the price source row exists before resolving source_products.
    await pricing_repository.upsert_price_source(_SOURCE_CODE, "USD", "PriceCharting")

    # ── Collect accepted sales across every set with a sales file ─────────────
    accepted: list[dict] = []
    sets_with_sales = 0
    for set_info in pc_sets:
        sales_key = f"sales/{set_info['uid']}.json"
        if not await storage_service.file_exists(sales_key):
            continue
        sets_with_sales += 1
        sales_products = (await storage_service.load_json(sales_key)).get("products", {})
        accepted.extend(pc_staging.build_accepted_sales(sales_products, catalog))

    if not accepted:
        logger.info("pricecharting_stage_no_accepted_sales", extra={"sets": sets_with_sales})
        return {"accepted": 0, "inserted": 0, "sets": sets_with_sales, "source_products": 0}

    # ── Resolve a source_product_id for each matched card_version ─────────────
    cv_ids = [s["card_version_id"] for s in accepted]
    cv_to_spid = await pricing_repository.upsert_source_products_for_cards(cv_ids, _SOURCE_CODE)

    # ── Insert each accepted sale (idempotent on item_id) ─────────────────────
    inserted = skipped_no_spid = 0
    for sale in accepted:
        spid = cv_to_spid.get(sale["card_version_id"])
        if spid is None:
            skipped_no_spid += 1
            continue
        await ebay_scrape_repository.insert_scraped_sold(
            item_id=sale["item_id"],
            title=sale["title"],
            source_product_id=spid,
            price_cents=sale["price_cents"],
            currency=sale["currency"],
            marketplace_id=sale["marketplace_id"],
            condition_id=sale["condition_id"],
            finish_id=sale["finish_id"],
            language_id=sale["language_id"],
            sold_at=sale["sold_at"],
        )
        inserted += 1

    logger.info(
        "pricecharting_stage_complete",
        extra={
            "sets": sets_with_sales,
            "accepted": len(accepted),
            "inserted": inserted,
            "source_products": len(cv_to_spid),
            "skipped_no_source_product": skipped_no_spid,
        },
    )
    return {
        "accepted": len(accepted),
        "inserted": inserted,
        "sets": sets_with_sales,
        "source_products": len(cv_to_spid),
        "skipped_no_source_product": skipped_no_spid,
    }
