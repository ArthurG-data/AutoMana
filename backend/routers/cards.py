from uuid import UUID
import logging
from fastapi import APIRouter, Depends, Path, HTTPException, Query
from typing import Annotated, Union, Sequence, Optional, List
from backend.dependancies import get_token_header
from backend.models.cards import BaseCard, CreateCard
from backend.database.database_utilis import create_delete_query,create_insert_query,create_select_query,create_update_query, execute_select_query, execute_delete_query
from backend.dependancies import cursorDep
from psycopg2.extensions import connection


router = APIRouter(
    prefix='/cards',
    tags=['cards'],
    dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)


        
    #query = create_select_query('card_version',['card_version_id'], conditions_list=['card_version_id = %s'])

def get_cards_info(conn: connection,
                        card_id : Optional[UUID|Sequence[UUID]]=None, 
                        limit : Annotated[int, Query(le=100)]=100,
                        offset: int = 0,
                        select_all : bool = True)-> Union[List[BaseCard] , BaseCard]:
    is_list = isinstance(card_id, list)  
    query = """ SELECT uc.card_name, r.rarity_name, s.set_name,s.set_code, uc.cmc, cv.oracle_text, s.released_at, s.digital, r.rarity_name
            FROM unique_cards uc
            JOIN card_version cv ON uc.unique_card_id = cv.unique_card_id
            JOIN rarities r ON cv.rarity_id = r.rarity_id
            JOIN sets s ON cv.set_id = s.set_id """
    if is_list:
        query += "WHERE cv.card_version_id = ANY(%s) LIMIT %s OFFSET %s;"
        values = ((card_id ), limit , offset)
    elif card_id:
        query += "WHERE cv.card_version_id = %s LIMIT %s OFFSET %s"
        values = (card_id , limit , offset)
    else:
        query += "LIMIT %s OFFSET %s "
        values = (limit , offset)
    query += ";"

    try:
        cards = execute_select_query(conn, query, values, execute_many=False, select_all=select_all)
        return cards
    except Exception:
        raise
    

@router.post('/', response_model=None)
async def add_card(cards : List[CreateCard]):
    query = """ WITH
                ins_unique_card AS (
                INSERT INTO unique_cards_ref (card_name, cmc, mana_cost, reserved)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (card_name) DO NOTING
                RETURNING unique_card_id
                ),
                get_unique_card AS (
                SELECT unique_card_id FROM ins_unique_card
                UNION
                SELECT unique_card_id FROM unique_cards_ref WHERE card_name = %s
                ),
                ins_border_color AS (
                INSERT INTO  border_color_ref (border_color_name)
                VALUES (%s)
                ON CONFLICT (boder_color_name) DO NOTHING
                RETURNING border_color_id
                ),
                get_border_id AS (
                SELECT border_color_id FROM ins_border_color
                UNION
                SELECT border_color_id FROM border_color_ref WHERE border_color_ref = %s
                ),
                ins_rarity AS (
                INSERT INTO rarities rarity
                VALUES (%s)
                ON CONFLICT (rarity_name) DO NOTHING
                RETURNING rarity_id
                ),
                get_rarity_id AS (
                SELECT rarity id from ins_rarity
                UNION
                SELECT rarity_id FROM rarities WHERE rarity_name = %s
                ),
                ins_artist_id AS (
                INSERT INTO artists_ref (artist_name)
                VALUES (%s)
                ON CONFLICT (artist_name) DO NOTTHING   
                RETURNING artist_id
                ),
                get_artist_id AS (
                SELECT artist_id from ins_artist_id
                UNION
                SELECT artist_id from artists_ref WHERE artist_name = %s
                ),
                ins_frame_id AS (
                INSERT INTO frames_ref frame_year
                VALUES (%s)
                ON CONFLICT (frame_year) DO NOTHING
                RETURNING frame_id
                ),
                get_frame_id AS (
                SELECT frame_id FROM ins_frame_id
                UNION
                SELECT frame_id from frames_ref WHERE frame_year = %s
                ),
                ins_layout_id AS (
                INSERT INTO layout_ref layout_name
                VALUES (%s)
                ON CONFLICT (layout_name) DO NOTHING
                RETURNING layout_id 
                ),
                get_layout_id AS (
                SELECT layout_id FROM ins_layout_id
                UNION
                SELECT layout_id FROM layout_ref WHERE layout_name = %s
                ),
                ins

    """
    return {"received": len(cards), "cards": cards}
 
@router.get('/{card_id}', response_model=BaseCard)
async def get_card_info(card_id : str, limit : int=100, offset : int=0 , conn : connection=Depends(cursorDep)):
    return  get_cards_info(conn, card_id, limit, offset, select_all=False )
    
@router.get('/', response_model=List[BaseCard])
async def get_all_cards(limit : int=100, offset : int=0 , conn : connection=Depends(cursorDep)):
    return  get_cards_info(conn, limit=limit, offset=offset , select_all=True)

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

async def read_card(card_id : Annotated[str, Path(title='The unique version id of the card to get', min_length=36, max_length=36)],  connection: cursorDep ) -> list[BaseCard]  :
    query = create_select_query('card_version',['card_version_id'], conditions_list=['card_version_id = %s'])
    #query =  """ SELECT * FROM card_version WHERE card_version_id = %s """ 
    logging.info("🔹 Route handler started!")
    try:
        card =  execute_select_query(connection, query, (card_id, 10, 0))
        if card:
            return {'unique_id': card_id, 'version_id' : card}
        else :
            raise HTTPException(status_code=404, detail="Card ID not found")
    except Exception as e:
        return {'card-id' : card_id, 'error':str(e)}
    
class CommonQueryParams:
    def __init__ (self, q : str | None=None, skip: Annotated[int, Query(ge=0)] =0, limit: Annotated[int , Query(ge=1, le=50)]= 10):
        self.q = q,
        self.skip = skip,
        self.limit = limit

