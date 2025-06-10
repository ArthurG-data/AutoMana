from backend.modules.internal.cards.models import CreateCard, CreateCards
from psycopg2.extensions import connection, cursor
from backend.database.database_utilis import execute_insert_query
from backend.modules.internal.cards import queries 
from psycopg2.extras import execute_values, Json
from backend.modules.internal.cards import utils
from backend.modules.internal.cards import services
import uuid

async def add_card(conn: connection,  card : CreateCard):
    values =  (
            card.card_name,
            card.cmc,
            card.mana_cost,
            card.reserved,
            card.oracle_text,
            card.set_name,
            str(card.collector_number),
            card.rarity_name,
            card.border_color,
            card.frame,
            card.layout,
            card.is_promo,
            card.is_digital,
            Json(card.card_color_identity),        # p_colors
            card.artist,
            card.artist_ids[0] if card.artist_ids else uuid.UUID("00000000-0000-0000-0000-000000000000"),
            Json(card.legalities),
            card.illustration_id,
            Json(card.types),
            Json(card.supertypes),
            Json(card.subtypes),
            Json(card.games),
            card.oversized,
            card.booster,
            card.full_art,
            card.textless,
            str(card.power) if card.power is not None else None,
            str(card.toughness) if card.toughness is not None else None,
            Json(card.promo_types),
            card.variation,
            utils.to_json_safe([f.model_dump() for f in card.card_faces]) if card.card_faces else Json([])
        )
    

    try:
        with conn.cursor() as cur:
            cur.execute(queries.insert_full_card_query, values)
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        return {'error:': str(e)}


    
async def add_cards(conn: connection, new_cards : CreateCards):
    values_list = []
    for card in new_cards.items:
        values = (
            card.card_name,
            card.cmc,
            card.mana_cost,
            card.reserved,
            card.oracle_text,
            card.set_name,
            str(card.collector_number),
            card.rarity_name,
            card.border_color,
            card.frame,
            card.layout,
            card.is_promo,
            card.is_digital,
            Json(card.card_color_identity),        # p_colors
            card.artist,
            card.artist_ids[0] if card.artist_ids else uuid.UUID("00000000-0000-0000-0000-000000000000"),
            Json(card.legalities),
            card.illustration_id,
            Json(card.types),
            Json(card.supertypes),
            Json(card.subtypes),
            Json(card.games),
            card.oversized,
            card.booster,
            card.full_art,
            card.textless,
            str(card.power) if card.power is not None else None,
            str(card.toughness) if card.toughness is not None else None,
            Json(card.promo_types),
            card.variation,
            utils.to_json_safe([f.model_dump() for f in card.card_faces]) if card.card_faces else Json([])
        )
        values_list.append(values)
    try:
        with conn.cursor() as cursor:
            cursor.executemany(queries.insert_full_card_query, values_list)
            conn.commit()
    except Exception:
        raise
    
def add_cards_bulk(new_cards : CreateCards, conn: connection):
    values_list = []
    for item in new_cards.items:
        data = item.model_dump()
        values = tuple(v for _, v in data.items())
        values_list.append(values)
    return execute_insert_query(conn, queries.insert_full_card_query, values_list, execute_many=True)
    
def insert_card_batch(conn : connection, cursor : cursor, cards : CreateCards):
    print(f"Inserting batch of {cards.count} cards...")
    for card in cards.items:
        values = (
            card.card_name,
            card.cmc,
            card.mana_cost,
            card.reserved,
            card.oracle_text,
            card.set_name,
            str(card.collector_number),
            card.rarity_name,
            card.border_color,
            card.frame,
            card.layout,
            card.is_promo,
            card.is_digital,
            Json(card.card_color_identity),
            card.artist,
            card.artist_ids[0] if card.artist_ids else uuid.UUID("00000000-0000-0000-0000-000000000000"),
            Json(card.legalities),
            card.illustration_id,
            Json(card.types),
            Json(card.supertypes),
            Json(card.subtypes),
            Json(card.games),
            card.oversized,
            card.booster,
            card.full_art,
            card.textless,
            str(card.power) if card.power is not None else None,
            str(card.toughness) if card.toughness is not None else None,
            Json(card.promo_types),
            card.variation,
            Json(utils.to_json_safe([f.model_dump() for f in card.card_faces]))
        )
        cursor.execute(queries.insert_full_card_query, values)
    conn.commit()