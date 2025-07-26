from fastapi import APIRouter, Depends
from backend.services_old.shop_data_ingestion.models.shopify_models import Market
from backend.request_handling.ApiHandler import ApiHandler
market_router = APIRouter(prefix="/market", tags=["Market"])

api: ApiHandler = ApiHandler()

@market_router.post("/")
async def post_market(values: Market.InsertMarket):
    return await api.execute_service("shop_meta.market.add", values=values)

@market_router.get("/{market_id}")
async def get_market(market_id: int):
    return await api.execute_service("shop_meta.market.get", id=market_id)

@market_router.get("/")
async def get_all_markets():
    return await api.execute_service("shop_meta.market.get")



