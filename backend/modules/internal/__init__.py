from fastapi import APIRouter
from backend.modules.internal.auth.routers import authentification_router
#need to be hidden after testing
internal_router = APIRouter(prefix='/internal', tags=['internal'])

internal_router.include_router(authentification_router)