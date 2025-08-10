from fastapi import APIRouter
from . import users #card_reference, set_reference, collection, users

api_router = APIRouter(prefix="/public", tags=["API", "Public"])

#api_router.include_router(card_reference.card_reference_router)
#api_router.include_router(set_reference.router)
#api_router.include_router(collection.router)
api_router.include_router(users.router)

