import logging
from typing import Optional

from automana.core.models.shopify.Market import InsertMarket
from automana.core.repositories.app_integration.shopify.market_repository import MarketRepository
from automana.core.framework.registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="shop_meta.market.add",
    db_repositories=["market"],
)
async def add(market_repository: MarketRepository, values: InsertMarket):
    await market_repository.add(values)
    return {"status": "success", "name": values.name}


@ServiceRegistry.register(
    path="shop_meta.market.get",
    db_repositories=["market"],
)
async def get(market_repository: MarketRepository, id: Optional[int] = None):
    markets = await market_repository.list()
    if id:
        market = next((m for m in markets if m.get("market_id") == id), None)
        if not market:
            return {"status": "error", "message": "Market not found"}
        return {"status": "success", "market": market}
    return {"status": "success", "market": markets}
