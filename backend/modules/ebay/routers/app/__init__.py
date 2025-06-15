from fastapi import APIRouter
from backend.modules.ebay.routers.app import app, listing

ebay_app_router = APIRouter(prefix='/app/{app_id}', tags=['app'])

ebay_app_router.include_router(app.app_router)
ebay_app_router.include_router(listing.ebay_listing_router)

