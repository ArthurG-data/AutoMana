from fastapi import APIRouter, Response, HTTPException
from backend.api.admin.app_integration.ebay import router as ebay_router

router = APIRouter(
    prefix='/app_integration',
    tags=['app_integration'],
    responses={404:{'description' : 'Not found'}}
)

router.include_router(ebay_router)
