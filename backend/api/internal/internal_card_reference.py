import os, shutil
from fastapi import APIRouter
from backend.modules.internal.cards import services as cards_services

from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks
from backend.database.get_database import cursorDep
from typing import List
from backend.modules.internal.cards.utils import cards_from_json
from backend.modules.internal.cards.models import CreateCard, CreateCards
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_delete_query
from backend.modules.internal.cards import services
from backend.services_old.shop_data_ingestion.upload.card_batch_importer import process_large_cards_json
from uuid import UUID 

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(
    prefix='/cards-reference',
    tags=['intern-cards'],
    #dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)

@router.post('/', response_model=None)
async def insert_card(conn: cursorDep,  card : CreateCard):
    return await cards_services.add_card(conn, card)

@router.post('/bulk')
async def insert_cards(conn : cursorDep, cards : List[CreateCard]):
    cards : CreateCards = CreateCards(items=cards)
    await cards_services.add_cards(conn, cards)


@router.post('/from_json')
async def insert_cards_json(conn: cursorDep, parsed_cards : CreateCards = Depends(services.get_parsed_cards)):
        await services.add_cards_bulk(parsed_cards, conn)
     
@router.post("/large_json")
async def upload_large_cards_json( file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    await services.upload_large_cards_json(file, background_tasks)
    
@router.delete('/{card_id}')
async def delete_card(card_id : UUID, conn : connection=Depends(cursorDep)):
    await services.delete_card(card_id, conn)