from fastapi import APIRouter, Depends
from backend.schemas.external_marketplace.shopify import Market
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager

market_router = APIRouter(prefix="/market", tags=["Market"])

@market_router.post("/")
async def post_market(
    values: Market.InsertMarket,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service("shop_meta.market.add", values=values)

@market_router.get("/{market_id}")
async def get_market(
    market_id: int,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service("shop_meta.market.get", id=market_id)

@market_router.get("/")
async def get_all_markets(
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service("shop_meta.market.get")



