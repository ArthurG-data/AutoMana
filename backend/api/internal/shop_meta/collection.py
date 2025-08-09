from fastapi import APIRouter, Depends
from backend.schemas.external_marketplace.shopify import shopify_theme
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager

collection_router = APIRouter(prefix="/collection", tags=["Collection"])


@collection_router.post("/")
async def post_collection(
    values: shopify_theme.InsertCollection,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    """
    Insert a new collection into the database.
    If the collection already exists, it will not be inserted again.
    """
    return await service_manager.execute_service("shop_meta.collection.add", values=values)

@collection_router.post("/bulk")
async def post_bulk_collections(
    values: list[shopify_theme.InsertCollection],
    service_manager: ServiceManager = Depends(get_service_manager)
):
    """
    Insert multiple collections into the database.
    If a collection already exists, it will not be inserted again.
    """
    return await service_manager.execute_service("shop_meta.collection.add_many", values=values)
