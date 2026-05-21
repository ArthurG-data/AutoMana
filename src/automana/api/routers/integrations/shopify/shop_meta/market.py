from fastapi import APIRouter
from automana.core.models.shopify import Market
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.dependancies.auth.users import AdminUserDep, CurrentUserDep

market_router = APIRouter(prefix="/market", tags=["Market"])

@market_router.post("/")
async def post_market(
    values: Market.InsertMarket,
    _admin: AdminUserDep,
    service_manager: ServiceManagerDep,
):
    return await service_manager.execute_service("shop_meta.market.add", values=values)

@market_router.get("/{market_id}")
async def get_market(
    market_id: int,
    _user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    return await service_manager.execute_service("shop_meta.market.get", id=market_id)

@market_router.get("/")
async def get_all_markets(
    _user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    return await service_manager.execute_service("shop_meta.market.get")
