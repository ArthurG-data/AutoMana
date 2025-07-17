from fastapi import APIRouter, Depends
from backend.database.get_database import cursorDep
from backend.modules.public.cards.models import CreateCard
from psycopg2.extensions import connection
from uuid import UUID
from backend.modules.internal.cards.services import add_card as add_card_service,add_cards as add_cards_service

router = APIRouter(
    prefix='/card-reference',
    tags=['admin-cards'],
    #dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)

from psycopg2.extras import execute_values

@router.post('/', response_model=None)
async def insert_card(card: CreateCard, conn: cursorDep):
    return await add_card_service(conn, card)

    
@router.delete('/{card_id}')
async def delete_card(card_id : UUID, conn : connection=Depends(cursorDep)):
    return await delete_card_service(card_id, conn)
    