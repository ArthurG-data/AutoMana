from fastapi import APIRouter
from backend.modules.ebay.routers import app,auth, dev,inventory,listing,orders,stores

ebay_router = APIRouter(prefix='/ebay', tags=['ebay'])

ebay_router.include_router(app.ebay_app_router)
ebay_router.include_router(auth.ebay_auth_router)
ebay_router.include_router(dev.ebay_dev_router)
ebay_router.include_router(listing.ebay_listing_router)
