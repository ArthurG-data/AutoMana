from fastapi import APIRouter, Depends
from backend.database.get_database import cursorDep
from backend.modules.internal.cards.models import CreateCard
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_delete_query
from backend.modules.internal.cards.utils import to_json_safe
from backend.modules.internal.cards.services import add_card
from uuid import UUID
from typing import List
from psycopg2.extras import execute_values, Json


router = APIRouter(
    prefix='/cards',
    tags=['intern-cards'],
    #dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)


@router.post('/', response_model=None)
async def insert_card(conn: cursorDep,  card : CreateCard):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT insert_full_card_version(
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            );
        """, (
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
            card.artist_ids[0] if card.artist_ids else None,
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
            to_json_safe([f.model_dump() for f in card.card_faces]) if card.card_faces else Json([])
        ))
        conn.commit()
        return cur.fetchone()
    return await add_card(conn, card)

@router.post('/bulk/')
async def insert_cards(conn : cursorDep, cards : List[CreateCard]):
    return cards
    pass
    
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
