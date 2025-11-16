from fastapi import APIRouter
from backend.api.catalog import catalog_router
from backend.api.users import user_router
from backend.api.integrations import integrations_router
from backend.api.logs.logs import log_router

api_router = APIRouter(prefix="/api", tags=["API"])
    
api_router.include_router(catalog_router)
api_router.include_router(user_router)
api_router.include_router(integrations_router)
api_router.include_router(log_router)