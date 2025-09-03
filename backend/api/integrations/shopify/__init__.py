from fastapi import APIRouter
from backend.api.integrations.shopify.shop_meta import shop_metadata_router


shopify_router = APIRouter(prefix="/shopify", tags=["Shopify"])
shopify_router.include_router(shop_metadata_router)
