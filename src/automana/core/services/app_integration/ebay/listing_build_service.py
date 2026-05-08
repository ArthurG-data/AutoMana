from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from automana.core.models.ebay.listing_inputs import (
    BrandConfig,
    Condition,
    DescriptionMode,
    PricingInput,
    SellerInput,
)
from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import (
    EbaySellingRepository,
)
from automana.core.repositories.app_integration.ebay.listing_builder_repository import (
    EbayListingBuilderRepository,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay.listing_builder import build_mtg_listing
from automana.core.services.app_integration.ebay.listings_write_service import (
    create_listing,
)

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.build_and_create",
    db_repositories=["auth", "listing_builder"],
    api_repositories=["selling"],
)
async def build_and_create_listing(
    auth_repository: EbayAuthRepository,
    listing_builder_repository: EbayListingBuilderRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    card_version_id: UUID,
    condition: str,
    quantity: int,
    price_aud: str,
    foil: bool = False,
    lang: str = "en",
    shipping_cost_aud: str = "0.00",
    condition_note: Optional[str] = None,
    description_mode: str = "full",
    brand_config: Optional[Dict[str, Any]] = None,
    marketplace_id: str = "15",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Fetch card data, build the ItemModel, and submit it to eBay.

    price_aud and shipping_cost_aud are strings to survive JSON serialisation
    through Celery task arguments; converted to Decimal here.
    """
    card_data = await listing_builder_repository.fetch_card_data(card_version_id)
    if card_data is None:
        raise ValueError(f"Card version {card_version_id} not found in card_catalog")

    try:
        condition_enum = Condition(condition.upper())
    except ValueError:
        raise ValueError(
            f"Invalid condition '{condition}'. Must be one of: "
            + ", ".join(c.value for c in Condition)
        )

    seller_input = SellerInput(
        condition=condition_enum,
        quantity=quantity,
        foil=foil,
        lang=lang,
        price_aud=Decimal(price_aud),
        shipping_cost_aud=Decimal(shipping_cost_aud),
        condition_note=condition_note,
        description_mode=DescriptionMode(description_mode),
    )

    brand = BrandConfig(**(brand_config or {})) if brand_config else BrandConfig()

    pricing = PricingInput(
        buy_it_now_price_aud=Decimal(price_aud),
        domestic_shipping_cost_aud=Decimal(shipping_cost_aud),
    )

    item = build_mtg_listing(card_data, seller_input, brand, pricing)
    idempotency_key = str(uuid4())

    logger.info(
        "ebay_build_and_create_listing",
        extra={
            "user_id": str(user_id),
            "app_code": app_code,
            "card_version_id": str(card_version_id),
            "condition": condition,
            "foil": foil,
            "lang": lang,
            "idempotency_key": idempotency_key,
        },
    )

    return await create_listing(
        auth_repository=auth_repository,
        selling_repository=selling_repository,
        user_id=user_id,
        app_code=app_code,
        item=item,
        idempotency_key=idempotency_key,
        marketplace_id=marketplace_id,
    )
