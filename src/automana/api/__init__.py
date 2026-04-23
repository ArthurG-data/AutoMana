from fastapi import APIRouter
from automana.api.routers.catalog import catalog_router
from automana.api.routers.users import user_router
from automana.api.routers.integrations import integrations_router
from automana.api.routers.ops import ops_router

api_router = APIRouter(prefix="/api", tags=["API"])

api_router.include_router(catalog_router)
api_router.include_router(user_router)
api_router.include_router(integrations_router)
api_router.include_router(ops_router)
