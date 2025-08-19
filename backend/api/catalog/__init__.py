from fastapi import APIRouter
from backend.api.catalog.mtg import mtg_router

catalog_router = APIRouter(prefix="/catalog", tags=["Catalog"])
catalog_router.include_router(mtg_router)