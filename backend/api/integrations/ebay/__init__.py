from fastapi import APIRouter
from backend.api.integrations.ebay.ebay_auth import ebay_auth_router
from backend.api.integrations.ebay.ebay_browse import search_router
from backend.api.integrations.ebay.ebay_selling import ebay_listing_router
ebay_router = APIRouter(prefix="/ebay", tags=["eBay"])

ebay_router.include_router(ebay_auth_router)
ebay_router.include_router(search_router)
ebay_router.include_router(ebay_listing_router)