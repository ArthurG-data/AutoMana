from fastapi import APIRouter
from backend.api.integrations.ebay import ebay_router
from backend.api.integrations.shopify import shopify_router
from backend.api.integrations.mtg_stock import router as mtg_stock_router

integrations_router = APIRouter(prefix="/integrations", tags=["Integrations"])
integrations_router.include_router(ebay_router) 
integrations_router.include_router(shopify_router)
integrations_router.include_router(mtg_stock_router)