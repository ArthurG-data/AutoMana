"""Sealed product pricing service steps."""
from __future__ import annotations

import logging
from datetime import date

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.mtgjson.Apimtgjson_repository import ApimtgjsonRepository
from automana.core.repositories.pricing.sealed_pricing_repository import SealedPricingRepository

logger = logging.getLogger(__name__)

# External identifiers that MTGJson exposes on sealedProduct.identifiers.
# Keys are AutoMana identifier names; values are MTGJson identifier field names.
_MTGJSON_IDENTIFIER_MAP = {
    "tcgplayer_product_id": "tcgplayerProductId",
    "cardkingdom_id":        "cardKingdomId",
    "mcm_id":               "mcmId",
    "scg_id":               "scgId",
    "abu_id":               "abuId",
}


@ServiceRegistry.register(
    "pricing.sealed.bootstrap_catalog_from_set",
    db_repositories=["sealed_pricing"],
    api_repositories=["mtgjson"],
)
async def bootstrap_sealed_catalog_from_set(
    sealed_pricing_repository: SealedPricingRepository,
    mtgjson_repository: ApimtgjsonRepository,
    set_code: str,
) -> dict:
    """Fetch a MTGJson set JSON and upsert its sealedProduct[] into the catalog.

    Pulls type/subtype from the MTGJson taxonomy and maps every available
    external identifier (tcgplayerProductId, cardKingdomId, etc.) into
    card_catalog.sealed_external_identifier. Creates the pricing.product_ref +
    pricing.mtg_sealed_products rows so prices can be written once we have a
    source for them.

    Returns a summary dict with counts for logging/pipeline context.
    """
    logger.info("Fetching MTGJson set JSON for sealed catalog", extra={"set_code": set_code})
    raw = await mtgjson_repository.fetch_set_json(set_code)
    sealed_products_raw = raw.get("data", {}).get("sealedProduct", [])

    if not sealed_products_raw:
        logger.warning("No sealedProduct entries in MTGJson set", extra={"set_code": set_code})
        return {"set_code": set_code, "total": 0, "upserted": 0, "skipped_no_uuid": 0}

    products: list[dict] = []
    skipped = 0
    for raw_product in sealed_products_raw:
        mtgjson_uuid = raw_product.get("uuid")
        if not mtgjson_uuid:
            skipped += 1
            continue

        identifiers = raw_product.get("identifiers") or {}
        product: dict = {
            "mtgjson_uuid":   mtgjson_uuid,
            "name":           raw_product.get("name", ""),
            "set_code":       set_code,
            "game_code":      "mtg",
            "language_code":  "en",
            "type_code":      raw_product.get("category", ""),
            "subtype_code":   raw_product.get("subtype") or "",
            "release_date":   _parse_date(raw_product.get("releaseDate")),
        }
        for our_key, mtgjson_key in _MTGJSON_IDENTIFIER_MAP.items():
            value = identifiers.get(mtgjson_key)
            if value:
                product[our_key] = value

        products.append(product)

    upserted = await sealed_pricing_repository.upsert_sealed_catalog(products)
    logger.info(
        "Sealed catalog upserted",
        extra={"set_code": set_code, "upserted": upserted, "skipped_no_uuid": skipped},
    )
    return {
        "set_code":        set_code,
        "total":           len(sealed_products_raw),
        "upserted":        upserted,
        "skipped_no_uuid": skipped,
    }


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


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
