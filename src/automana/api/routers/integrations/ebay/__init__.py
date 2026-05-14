from fastapi import APIRouter
from automana.api.routers.integrations.ebay.ebay_auth import ebay_auth_router
from automana.api.routers.integrations.ebay.ebay_browse import search_router
from automana.api.routers.integrations.ebay.ebay_selling import ebay_listing_router
from automana.api.routers.integrations.ebay.scopes import router as scopes_router
from automana.api.routers.integrations.ebay.ebay_market import market_router
from automana.api.routers.integrations.ebay.ebay_recommendations import router as recommendations_router

ebay_router = APIRouter(prefix="/ebay", tags=["eBay"])

ebay_router.include_router(ebay_auth_router)
ebay_router.include_router(search_router)
ebay_router.include_router(ebay_listing_router)
ebay_router.include_router(scopes_router)
ebay_router.include_router(market_router)
ebay_router.include_router(recommendations_router, prefix="/recommendations", tags=["recommendations"])
