from backend.modules.internal.cards.models import CreateCard
from psycopg2.extensions import connection
from psycopg2.extras import execute_values
from backend.database.database_utilis import execute_insert_query
from backend.modules.internal.cards.queries import main_insert_query

async def add_card(conn: connection,  card : CreateCard):

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
        execute_insert_query("SELECT insert_full_card_version ()")
    except Exception:
        raise