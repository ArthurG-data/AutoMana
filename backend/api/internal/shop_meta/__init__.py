from fastapi import APIRouter
from . import theme_router, collection_router

shop_metadata_router = APIRouter(prefix="/shop-meta", tags=["Shop Metadata"])

shop_metadata_router.include_router(theme_router.theme_router)
shop_metadata_router.include_router(collection_router.collection_router)