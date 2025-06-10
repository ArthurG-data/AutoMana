from fastapi import APIRouter, Depends
from backend.database.get_database import cursorDep
from backend.modules.public.cards.models import CreateCard
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_delete_query
from uuid import UUID

router = APIRouter(
    prefix='/cards',
    tags=['admin-cards'],
    #dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)

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
