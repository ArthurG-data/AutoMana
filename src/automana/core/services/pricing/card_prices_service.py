import logging
from uuid import UUID

from automana.core.models.card_catalog.price_history import CardPriceEntry, CardPricesResponse
from automana.core.framework.registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "pricing.card.get_prices",
    db_repositories=["pricing", "card"],
)
async def get_card_prices(
    pricing_repository,
    card_repository,
    card_version_id: UUID,
) -> CardPricesResponse:
    """Return current prices and purchase URIs for a card version."""
    price_rows, purchase_uris = await _fetch(
        pricing_repository, card_repository, card_version_id
    )

    entries = [
        CardPriceEntry(
            source=r["source"],
            finish=r["finish"],
            condition=r["condition"],
            language=r["language"],
            price_date=r["price_date"],
            market_cents=r["market_cents"],
            low_cents=r["low_cents"],
        )
        for r in price_rows
    ]

    return CardPricesResponse(
        card_version_id=card_version_id,
        purchase_uris=purchase_uris,
        prices=entries,
    )


async def _fetch(pricing_repository, card_repository, card_version_id):
    prices = await pricing_repository.get_card_current_prices(card_version_id)
    purchase_uris = await card_repository.get_purchase_uris(card_version_id)
    return prices, purchase_uris
