from fastapi import APIRouter, Depends
from backend.services.shop_data_ingestion.models import shopify_theme
from backend.services.shop_data_ingestion.shop_metadata import shop_metadata_services
from backend.services.shop_data_ingestion.db.dependencies import get_sync_query_executor
from backend.services.shop_data_ingestion.db import QueryExecutor
from backend.request_handling.ApiHandler import ApiHandler
theme_router = APIRouter(prefix="/theme", tags=["Theme"])
api = ApiHandler()

@theme_router.post("/")
async def post_theme(values: shopify_theme.InsertTheme):
    #shop_metadata_services.insert_theme(values, queryExecutor)
    await api.execute_service("shop_meta.theme.add", values=values)

@theme_router.post("/collection")
def post_collection(values: shopify_theme.InsertCollectionTheme, queryExecutor: QueryExecutor.SyncQueryExecutor=Depends(get_sync_query_executor)):
    """
    Insert a new collection theme into the database.
    If the collection theme already exists, it will not be inserted again.
    """
    shop_metadata_services.insert_collection_theme(values, queryExecutor)







