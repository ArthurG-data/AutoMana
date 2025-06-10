from fastapi import APIRouter
from backend.modules.public.cards.router import router

card_router = APIRouter(
    prefix='/cards',
    tags=['cards'],
    responses={404:{'description' : 'Not found'}}
)

card_router.include_router(router)
