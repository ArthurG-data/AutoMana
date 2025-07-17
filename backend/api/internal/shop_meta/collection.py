from fastapi import APIRouter, Depends

from backend.services.shop_data_ingestion.models import shopify_models
from backend.services.shop_data_ingestion.shop_metadata import shop_metadata_services
from backend.services.shop_data_ingestion.db.QueryExecutor import SyncQueryExecutor
from backend.services.shop_data_ingestion.db.dependencies import get_sync_query_executor
from backend.request_handling.ApiHandler import ApiHandler

collection_router = APIRouter(prefix="/collection", tags=["Collection"])
api = ApiHandler()


@collection_router.post("/")
async def post_collection(values: shopify_models.InsertCollection):
    """
    Insert a new collection into the database.
    If the collection already exists, it will not be inserted again.
    """
    #shop_metadata_services.insert_collection(values, queryExecutor)
    return await api.execute_service("shop_meta.collection.add", values=values)

@collection_router.post("/bulk")
async def post_bulk_collections(values: list[shopify_models.InsertCollection], queryExecutor : SyncQueryExecutor=Depends(get_sync_query_executor)):
    """
    Insert multiple collections into the database.
    If a collection already exists, it will not be inserted again.
    """
    for value in values:
        shop_metadata_services.insert_collection(value, queryExecutor)
    return {"status": "success"}