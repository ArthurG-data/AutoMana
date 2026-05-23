from fastapi import APIRouter
from automana.core.models.shopify import shopify_theme
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.dependancies.auth.users import AdminUserDep


theme_router = APIRouter(prefix="/theme", tags=["Theme"])

@theme_router.post("/")
async def post_theme(
    values: shopify_theme.InsertTheme,
    _admin: AdminUserDep,
    service_manager: ServiceManagerDep,
):
    return await service_manager.execute_service("shop_meta.theme.add", values=values)

@theme_router.post("/collection")
async def post_collection(
    values: shopify_theme.InsertCollectionTheme,
    _admin: AdminUserDep,
    service_manager: ServiceManagerDep,
):
    return await service_manager.execute_service("shop_meta.theme.add_collection_theme", values=values)
