from fastapi import APIRouter, Depends
from backend.schemas.external_marketplace.shopify import shopify_theme
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager


theme_router = APIRouter(prefix="/theme", tags=["Theme"])

@theme_router.post("/")
async def post_theme(
    values: shopify_theme.InsertTheme,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    #shop_metadata_services.insert_theme(values, queryExecutor)
    await service_manager.execute_service("shop_meta.theme.add", values=values)

@theme_router.post("/collection")
async def post_collection(
    values: shopify_theme.InsertCollectionTheme,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    """
    Insert a new collection theme into the database.
    If the collection theme already exists, it will not be inserted again.
    """
    await service_manager.execute_service("shop_meta.theme.add_collection_theme", values=values)





