from fastapi import APIRouter
from typing import List
from uuid import UUID
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse
from backend.modules.public.cards.services import get_cards_info
from backend.request_handling.ApiHandler import ApiHandler
from backend.schemas.card_catalog.card import BaseCard

card_reference_router = APIRouter(
    prefix="/card-reference",
    tags=['cards'],
    responses={404:{'description' : 'Not found'}}
)

@card_reference_router.get('/{card_id}', response_model=ApiResponse[BaseCard])
async def get_card_info( card_id : UUID):
    return await ApiHandler.execute_service(
        "card_catalog.card.get",
        card_id=card_id
    )

@card_reference_router.get('/', response_model=PaginatedResponse[BaseCard])
async def get_all_cards(limit : int=100, offset : int=0 ):
    return await ApiHandler.execute_service(
        "card_catalog.card.list",
        limit=limit,
        offset=offset
    )
