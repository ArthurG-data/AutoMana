from fastapi import APIRouter, Depends

from backend.services.shop_data_ingestion.models import shopify_theme
from backend.request_handling.ApiHandler import ApiHandler

collection_router = APIRouter(prefix="/collection", tags=["Collection"])
api = ApiHandler()


@collection_router.post("/")
async def post_collection(values: shopify_theme.InsertCollection):
    """
    Insert a new collection into the database.
    If the collection already exists, it will not be inserted again.
    """
    return await api.execute_service("shop_meta.collection.add", values=values)

@collection_router.post("/bulk")
async def post_bulk_collections(values: list[shopify_theme.InsertCollection]):
    """
    Insert multiple collections into the database.
    If a collection already exists, it will not be inserted again.
    """
    return await api.execute_service("shop_meta.collection.add_many", values=values)
