from fastapi import APIRouter
from typing import List
from backend.modules.public.cards.models import BaseCard
from backend.database.get_database import cursorDep
from backend.modules.public.cards.services import get_cards_info


router = APIRouter(
    prefix="/card-reference",
    description="Card Database API",
    summary="Retrieve card information",
    tags=['cards'],
    responses={404:{'description' : 'Not found'}}
)

@router.get('/{card_id}', response_model=BaseCard)
async def get_card_info( conn : cursorDep, card_id : str, limit : int=100, offset : int=0):
    return  get_cards_info(conn, card_id, limit, offset, select_all=False )
    
@router.get('/', response_model=List[BaseCard])
async def get_all_cards(conn : cursorDep, limit : int=100, offset : int=0 ):
    return  get_cards_info(conn, limit=limit, offset=offset , select_all=True)