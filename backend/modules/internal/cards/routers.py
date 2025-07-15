from fastapi import APIRouter, Depends, UploadFile, Response, status, File, BackgroundTasks
from backend.database.get_database import cursorDep
from typing import List
from backend.modules.internal.cards.utils import cards_from_json
from backend.modules.internal.cards.models import CreateCard, CreateCards
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_delete_query
from backend.modules.internal.cards import services
from backend.services.shop_data_ingestion.upload.card_batch_importer import process_large_cards_json
from uuid import UUID

import os, shutil

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)



router = APIRouter(
    prefix='/cards',
    tags=['intern-cards'],
    #dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)


@router.post('/', response_model=None)
async def insert_card(conn: cursorDep,  card : CreateCard):
    return await services.add_card(conn, card)

@router.post('/bulk')
async def insert_cards(conn : cursorDep, cards : List[CreateCard]):
    cards : CreateCards = CreateCards(items=cards)
    await services.add_cards(conn, cards)
    return Response(status_code=status.HTTP_201_CREATED)

@router.post('/from_json')
async def insert_cards_json(conn: cursorDep, file: UploadFile = File(...)):
    try:
        parsed_cards : CreateCards = await cards_from_json(file)
        services.add_cards_bulk(parsed_cards, conn)
        return {'success'}
    except Exception as e:
        return {'error :' : str(e)}

@router.post("/large_json")
async def upload_large_cards_json( conn : cursorDep,file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    # Save file first
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Run background task to process it
    background_tasks.add_task(process_large_cards_json, file_path)

    return {"message": "File uploaded. Background processing started.", "filename": file.filename}

    
@router.delete('/{card_id}')
async def delete_card(card_id : UUID, conn : connection=Depends(cursorDep)):
    query = """
                BEGIN;
                WITH 
                delete_card_version AS (
                DELETE FROM card_version WHERE card_version_id = %s ON CASCADE
                RETURNING unique_card_id AS deleted_card_id
                ),
                DELETE FROM unique_card_ref 
                    WHERE unique_card_id IN (
                        SELECT deleted_card_id FROM delete_card_version
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM card_version
                        WHERE card_id IN (
                            SELECT deleted_card_id FROM delete_card_version
                    )
                );
                COMMIT;
"""
    try:
        return execute_delete_query(conn, query, (card_id,))
    except Exception:
        raise
