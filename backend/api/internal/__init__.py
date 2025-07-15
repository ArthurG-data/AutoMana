from fastapi import APIRouter
from . import shop_meta

internal_router = APIRouter(prefix="/internal", tags=["Internal"])

internal_router.include_router(shop_meta.shop_metadata_router)