from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from backend.modules.ebay.routers import app,auth, dev, inventory, listing, orders, stores
from backend.modules.auth.utils import check_token_validity

ebay_router = APIRouter(
    prefix='/ebay',
    tags=['ebay']
)

ebay_router.include_router(app.ebay_app_router)
ebay_router.include_router(auth.ebay_auth_router)
ebay_router.include_router(dev.ebay_dev_router)
ebay_router.include_router(listing.ebay_listing_router)

@ebay_router.get('/')
async def admin_root():
    return JSONResponse(content="You are an entering the ebay portal, brace yourself.")