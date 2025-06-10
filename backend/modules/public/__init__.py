from fastapi import APIRouter
from backend.modules.public import auth, cards, sets, users, collections

api_router = APIRouter(prefix='/api', tags=['public'])

api_router.include_router(auth.auth_router)
api_router.include_router(cards.card_router)
api_router.include_router(sets.sets_router)
api_router.include_router(users.user_router)
api_router.include_router(collections.collection_router)