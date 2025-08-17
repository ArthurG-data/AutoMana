from fastapi import APIRouter,  Response, HTTPException
from backend.api.admin.app_integration.ebay.scopes import router as scopes_router

router = APIRouter(
    prefix='/ebay',
    tags=['ebay'],
    responses={404:{'description' : 'Not found'}}
)

router.include_router(scopes_router)