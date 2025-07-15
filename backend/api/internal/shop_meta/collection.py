from fastapi import APIRouter

from backend.services.shop_data_ingestion.models import shopify_models
from backend.services.shop_data_ingestion.shop_metadata import shop_metadata_services
from backend.services.shop_data_ingestion.db import QueryExecutor

collection_router = APIRouter(prefix="/collection", tags=["Collection"])

@collection_router.post("/")
def post_collection(values: shopify_models.InsertCollection, queryExecutor: QueryExecutor.SyncQueryExecutor):
    """
    Insert a new collection into the database.
    If the collection already exists, it will not be inserted again.
    """
    shop_metadata_services.insert_collection(values, queryExecutor)