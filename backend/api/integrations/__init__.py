from fastapi import APIRouter
from backend.api.integrations.ebay import ebay_router

integrations_router = APIRouter(prefix="/integrations", tags=["Integrations"])
integrations_router.include_router(ebay_router) 