from fastapi import APIRouter
from automana.api.routers.mtg import mtg_router

# No tags here — child routers own their tags to avoid tag accumulation in Swagger.
catalog_router = APIRouter(prefix="/catalog")
catalog_router.include_router(mtg_router)
