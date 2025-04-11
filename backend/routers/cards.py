from uuid import UUID
import logging
from fastapi import APIRouter, Depends, Path, HTTPException, Query
from typing import Annotated, Union, Sequence, Optional, List
from backend.dependancies import get_token_header
from backend.models.cards import BaseCard, CreateCard
from backend.database.database_utilis import create_delete_query,create_insert_query,create_select_query,create_update_query, execute_select_query, execute_delete_query, execute_insert_query
from backend.dependancies import cursorDep
from psycopg2.extensions import connection


router = APIRouter(
    prefix='/cards',
    tags=['cards'],
    #dependencies=[Depends(get_token_header)],
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
    

from psycopg2.extras import execute_values

@router.post('/', response_model=None)
async def add_card(conn: cursorDep,  card : CreateCard):

    query_1 = """ 
            WITH
            ins_unique_card AS (
                INSERT INTO unique_cards_ref (card_name, cmc, mana_cost, reserved)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (card_name) DO NOTHING
                RETURNING unique_card_id
            """
    """
            ),
            get_unique_card AS (
                SELECT unique_card_id FROM ins_unique_card
                UNION
                SELECT unique_card_id FROM unique_cards_ref WHERE card_name = %s
            )
            SELECT FROM
            ,
            ins_border_color AS (
                INSERT INTO border_color_ref (border_color_name)
                VALUES (%s)
                ON CONFLICT (border_color_name) DO NOTHING
                RETURNING border_color_id
            ),
            get_border_id AS (
                SELECT border_color_id FROM ins_border_color
                UNION
                SELECT border_color_id FROM border_color_ref WHERE border_color_name = %s
            ),
            ins_rarity AS (
                INSERT INTO rarities_ref (rarity_name)
                VALUES (%s)
                ON CONFLICT (rarity_name) DO NOTHING
                RETURNING rarity_id
            ),
            get_rarity_id AS (
                SELECT rarity_id FROM ins_rarity
                UNION
                SELECT rarity_id FROM rarities_ref WHERE rarity_name = %s
            ),
            ins_artist AS (
                INSERT INTO artists_ref (artist_name)
                VALUES (%s)
                ON CONFLICT (artist_name) DO NOTHING
                RETURNING artist_id
            ),
            get_artist_id AS (
                SELECT artist_id FROM ins_artist
                UNION
                SELECT artist_id FROM artists_ref WHERE artist_name = %s
            ),
            ins_frame AS (
                INSERT INTO frames_ref (frame_year)
                VALUES (%s)
                ON CONFLICT (frame_year) DO NOTHING
                RETURNING frame_id
            ),
            get_frame_id AS (
                SELECT frame_id FROM ins_frame
                UNION
                SELECT frame_id FROM frames_ref WHERE frame_year = %s
            ),
            ins_layout AS (
                INSERT INTO layout_ref (layout_name)
                VALUES (%s)
                ON CONFLICT (layout_name) DO NOTHING
                RETURNING layout_id 
            ),
            get_layout_id AS (
                SELECT layout_id FROM ins_layout
                UNION
                SELECT layout_id FROM layout_ref WHERE layout_name = %s
            ),
            get_set_id AS (
                SELECT set_id FROM sets WHERE set_name = %s
            ),
            insert_card_version AS (
                INSERT INTO card_version (
                    unique_card_id, set_id, collector_number, rarity_id, 
                    border_color_id, frame_id, layout_id, oracle_text, 
                    is_promo, is_digital
                )
                SELECT 
                    guc.unique_card_id, gs.set_id, %s, gr.rarity_id, 
                    gb.border_color_id, gf.frame_id, gl.layout_id, %s,
                    %s, %s
                FROM get_unique_card guc
                CROSS JOIN get_set_id gs
                CROSS JOIN get_rarity_id gr
                CROSS JOIN get_border_id gb
                CROSS JOIN get_frame_id gf
                CROSS JOIN get_layout_id gl
                RETURNING card_version_id
            )
            SELECT card_version_id FROM insert_card_version;
    """

    query_2 = """
                WITH
                ins_keyword AS (
                INSERT INTO keywords_ref (keywords_name)
                ON CONFLICT (keyword_name) DO NOTHING
                RETURNING keyword_id
                ),
                get_keyword AS (
                SELECT keyword_id FROM ins_keyword
                UNION
                SELECT keyword_id FROM keyword_ref
                )
                INSERT INTO card_keyword (unique_card_id , keyword_id)
                VALUES (%s, keyword_id)
                FROM  get_keyword

    """
    query_3 = """
                WITH 
                ins_color AS (
                INSERT INTO colors_ref (color_name)
                ON CONFLICT (color_name) DO NOTHING
                RETURNING color_id
                ),
                get_color_ref AS (
                SELECT color_id FROM ins_color
                UNION
                SELECT color_id FROM colors_ref WHERE color_name = %s
                )
                INSERT INTO card_color_identity (unique_card_id, color_id)
                VALUES (%s, color_id)
                FROM get_color_ref
    """
    query_4 = """

    """
    values =  (
        card.card_name,
        card.cmc,
        card.mana_cost, 
        card.reserved, 
             
 
        # get_unique_card
        card.card_name,

        # border_color_ref
        card.border_color,

        # get_border_id
        card.border_color,
    

        # rarities_ref
        card.rarity_name,

        # get_rarity_id
        card.rarity_name,
    

        # artists_ref
        card.artist,

        # get_artist_id
        card.artist,


        # frames_ref
        card.frame,

        # get_frame_id
        card.frame ,
        # layout_ref
        card.layout,

        # get_layout_id
        card.layout,

        # sets
        card.set_name,

        # card_version
        
        card.oracle_text,
        str(card.collector_number),
        card.is_promo,
        card.is_digital)
   
    try:
        with conn.cursor() as cursor: 
            cursor.execute("""  WITH 
                ins_unique_card AS (INSERT INTO unique_cards_ref (card_name, cmc, mana_cost, reserved)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (card_name) DO NOTHING
                            RETURNING unique_card_id),
                get_card_id AS 
                           (SELECT unique_card_id FROM ins_unique_card
                            UNION
                            SELECT unique_card_id FROM unique_cards_ref WHERE card_name = %s),
                ins_border_color AS (
                            INSERT INTO border_color_ref (border_color_name)
                            VALUES (%s)
                            ON CONFLICT (border_color_name) DO NOTHING
                            RETURNING border_color_id
                ),
                get_border_id AS (
                           SELECT border_color_id FROM ins_border_color
                           UNION
                           SELECT border_color_id FROM border_color_ref WHERE border_color_name = %s
                           ),
                ins_rarity AS (
                            INSERT INTO rarities_ref (rarity_name)
                            VALUES (%s)
                            ON CONFLICT (rarity_name) DO NOTHING
                            RETURNING rarity_id
                ),
                get_rarity_id AS (
                            SELECT rarity_id FROM ins_rarity
                            UNION
                            SELECT rarity_id FROM rarities_ref WHERE rarity_name = %s
                ),
                ins_artist AS (
                            INSERT INTO artists_ref (artist_name)
                            VALUES (%s)
                            ON CONFLICT (artist_name) DO NOTHING
                            RETURNING artist_id
                ),
                get_artist_id AS (
                            SELECT artist_id FROM ins_artist
                            UNION
                            SELECT artist_id FROM artists_ref WHERE artist_name = %s
                ),
                ins_frame AS (
                            INSERT INTO frames_ref (frame_year)
                            VALUES (%s)
                            ON CONFLICT (frame_year) DO NOTHING
                            RETURNING frame_id
                ),
                get_frame_id AS (
                            SELECT frame_id FROM ins_frame
                            UNION
                            SELECT frame_id FROM frames_ref WHERE frame_year = %s
                ),
                ins_layout AS (
                            INSERT INTO layouts_ref (layout_name)
                            VALUES (%s)
                            ON CONFLICT (layout_name) DO NOTHING
                            RETURNING layout_id 
                ),
                get_layout_id AS (
                            SELECT layout_id FROM ins_layout
                            UNION
                            SELECT layout_id FROM layouts_ref WHERE layout_name = %s
                ),
                get_set_id AS (
                            SELECT set_id FROM sets WHERE set_name = %s
                ),
                insert_card_version AS (
                    INSERT INTO card_version (
                        unique_card_id, oracle_text, 
                        set_id, collector_number, 
                        rarity_id, border_color_id,
                        frame_id, layout_id, 
                        is_promo, is_digital
                    )
                    SELECT 
                        guc.unique_card_id, %s, gs.set_id, %s, gr.rarity_id, 
                        gb.border_color_id, gf.frame_id, gl.layout_id, %s,
                        %s
                    FROM get_card_id guc
                    CROSS JOIN get_set_id gs
                    CROSS JOIN get_rarity_id gr
                    CROSS JOIN get_border_id gb
                    CROSS JOIN get_frame_id gf
                    CROSS JOIN get_layout_id gl
                    RETURNING card_version_id
                )
                SELECT card_version_id FROM insert_card_version;
        
              """, values)
            unique_card_id = cursor.fetchone().get('card_version_id')
        
            if card.keywords:
            
                keyword_names = tuple(kw for kw in card.keywords)
            
                # fetch keyword_ids
                cursor.execute("INSERT INTO  keywords_ref (keyword_name) VALUES (%s) ON CONFLICT DO NOTHING", (keyword_names,))

                cursor.execute(
                    "SELECT keyword_id FROM keywords_ref WHERE keyword_name IN %s",
                    (keyword_names,)
                )
                #keyword_ids = [v for k, v in cursor.fetchall()]
                keyword_ids= [value.get('keyword_id') for value in cursor.fetchall()]

                #
                card_keyword_links = [(unique_card_id, kw_id) for kw_id in keyword_ids]
                # insert into mapping table
                execute_values(
                    cursor,
                    "INSERT INTO card_keyword (unique_card_id, keyword_id) VALUES %s ON CONFLICT (unique_card_id, keyword_id) DO NOTHING RETURNING unique_card_id, keyword_id",
                    card_keyword_links
                )
            color_name = tuple(cl for cl in card.card_color_identity)
            cursor.execute("INSERT INTO colors_ref (color_name) VALUES (%s) ON CONFLICT DO NOTHING ", (color_name,))
            cursor.execute("SELECT color_id FROM colors_ref WHERE color_name IN %s", (color_name,))
            color_ids = [value.get('color_id') for value in cursor.fetchall()]
            card_color_links = [(unique_card_id, cl_id) for cl_id in color_ids]
            execute_values(
                cursor,
                "INSERT INTO card_color_identity (unique_card_id, color_id) VALUES %s ON CONFLICT (unique_card_id, color_id) DO NOTHING",
                card_color_links
            )

            formats = tuple((k,) for k,v in card.legalities.items() if v != 'not_legal')
            status = tuple((v,) for _,v in card.legalities.items() if v != 'not_legal')
            
            execute_values(
                cursor,
                "INSERT INTO legal_status_ref (legal_status) VALUES %s ON CONFLICT (legal_status) DO NOTHING",
                status
            )
            cursor.execute("SELECT legality_id, legal_status FROM legal_status_ref WHERE legal_status IN %s", (status,))
            id_map = cursor.fetchall()
            id_map = {entry.get('legal_status'): entry.get('legality_id') for  entry in id_map}
            result = [id_map[s] for s in status]
            return result
            execute_values(
            cursor,
            "INSERT INTO formats_ref (format_name) VALUES %s ON CONFLICT (format_name) DO NOTHING",
            formats
            )
            cursor.execute("SELECT format_id FROM formats_ref WHERE format_name IN %s", (formats,))

            legality_dict = {}
            card_legality_links = [(unique_card_id, )]
            return cursor.fetchall()

    except Exception:
        raise
    

    #return {"received": len(cards), "cards": cards}
 
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

