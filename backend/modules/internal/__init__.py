from fastapi import APIRouter
from backend.modules.internal.auth.routers import authentification_router
from backend.modules.internal.cards.routers import router
from backend.modules.internal.sets.router import sets_router
#need to be hidden after testing
internal_router = APIRouter(prefix='/internal', tags=['internal'])

internal_router.include_router(authentification_router)
internal_router.include_router(router)
internal_router.include_router(sets_router)