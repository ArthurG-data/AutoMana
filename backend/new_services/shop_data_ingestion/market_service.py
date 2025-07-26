from backend.repositories.shop_meta.market_repository import MarketRepository
from backend.services_old.shop_data_ingestion.models.shopify_models.Market import InsertMarket, MarketInDb
from typing import List, Optional

async def add(repository : MarketRepository, values: InsertMarket):
    """Add a market to the database"""
    await repository.add(values)
    return {"status": "success", "name": values.name}

async def get(repository: MarketRepository, id: Optional[int] = None):
    """for now, cheat, do the filtering in the service layer"""
    market : List[MarketInDb] = await repository.list()

    if id:
        market = next((m for m in market if m.market_id == id), None)
    if market:
        return {"status": "success", "market": market}
    return {"status": "error", "message": "Market not found"}