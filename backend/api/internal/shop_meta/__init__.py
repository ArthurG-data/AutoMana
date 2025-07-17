from fastapi import APIRouter
from . import collection, theme

shop_metadata_router = APIRouter(prefix="/shop-meta", tags=["Shop Metadata"])

shop_metadata_router.include_router(theme.theme_router)
shop_metadata_router.include_router(collection.collection_router)