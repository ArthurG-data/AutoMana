from backend.repositories.shop_meta.market_repository import MarketRepository
from backend.services.shop_data_ingestion.models.shopify_models.Market import InsertMarket, MarketInDb
from typing import List

async def add(repository : MarketRepository, insert_market: InsertMarket):
    """Add a market to the database"""
    await repository.add_market(insert_market)
    return {"status": "success", "name": insert_market.name}

async def get(repository: MarketRepository, market_id: int):
    """for now, cheat, do the filtering in the service layer"""
    market : List[MarketInDb] = await repository.list_markets()
    market = next((m for m in market if m.market_id == market_id), None)
    if market:
        return {"status": "success", "market": market}
    return {"status": "error", "message": "Market not found"}