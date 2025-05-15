from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from backend.routers.ebay import router
from backend.routers.auth.utils import check_token_validity

ebay_router = APIRouter(
    prefix='/ebay',
    tags=['ebay']
)

ebay_router.include_router(router.router)

@ebay_router.get('/')
async def admin_root():
    return JSONResponse(content="You are an entering the ebay portal, brace yourself.")