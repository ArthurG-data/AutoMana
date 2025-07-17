from backend.modules.internal.cards.models import CreateCard, CreateCards
from psycopg2.extensions import connection, cursor
from backend.database.database_utilis import execute_insert_query
from backend.modules.internal.cards import queries 
from psycopg2.extras import  Json
from backend.modules.internal.cards import utils
from fastapi import UploadFile, File, HTTPException, BackgroundTasks
from backend.services.shop_data_ingestion.upload.card_batch_importer import process_large_cards_json
from backend.database.database_utilis import execute_delete_query
import uuid, os, shutil

UPLOAD_DIR = "uploads"

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

async def get_parsed_cards(file: UploadFile = File(...)) -> CreateCards:
    """Dependency that parses cards from an uploaded JSON file."""
    try:
        return await utils.cards_from_json(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid card JSON: {str(e)}")   
    
async def upload_large_cards_json( file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    # Save file first
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # Run background task to process it
    background_tasks.add_task(process_large_cards_json, file_path)

async def delete_card(card_id : uuid.UUID, conn : connection):
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
        execute_delete_query(conn, query, (card_id,))
    except Exception:
        raise

   