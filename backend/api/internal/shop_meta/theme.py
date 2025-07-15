from fastapi import APIRouter
from services.shop_data_ingestion.models import shopify_models
from services.shop_data_ingestion.shop_metadata import shop_metadata_services
from services.shop_data_ingestion.db import QueryExecutor

theme_router = APIRouter(prefix="/theme", tags=["Theme"])

@theme_router.post("/")
def post_theme(values: shopify_models.InsertTheme, queryExecutor: QueryExecutor.SyncQueryExecutor):
    shop_metadata_services.insert_theme(values, queryExecutor)

@theme_router.post("/collection")
def post_collection(values: shopify_models.InsertCollectionTheme, queryExecutor: QueryExecutor.SyncQueryExecutor):
    """
    Insert a new collection theme into the database.
    If the collection theme already exists, it will not be inserted again.
    """
    shop_metadata_services.insert_collection_theme(values, queryExecutor)







