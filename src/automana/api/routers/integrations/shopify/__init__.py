from fastapi import APIRouter
from automana.api.routers.integrations.shopify.shop_meta import shop_metadata_router
from automana.api.routers.integrations.shopify.data_loading import data_loading_router


shopify_router = APIRouter(prefix="/shopify", tags=["Shopify"])
shopify_router.include_router(shop_metadata_router)
shopify_router.include_router(data_loading_router)
