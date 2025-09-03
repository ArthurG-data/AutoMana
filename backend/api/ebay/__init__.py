from fastapi import APIRouter
from backend.api.ebay import auth, dev,inventory,orders,stores, app as app_router
from fastapi.responses import JSONResponse

ebay_router = APIRouter(prefix='/ebay', tags=['ebay'])

ebay_router.include_router(app_router.ebay_app_router)
ebay_router.include_router(auth.ebay_auth_router)
ebay_router.include_router(dev.ebay_dev_router)

@ebay_router.get('/')
async def admin_root():
    return JSONResponse(content="You are an entering the ebay portal, brace yourself.")

