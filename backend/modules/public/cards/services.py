from uuid import UUID
from fastapi import Query
from typing import Annotated, Union, Sequence, Optional, List
from backend.modules.public.cards.models import BaseCard
from backend.database.database_utilis import  execute_select_query
from psycopg2.extensions import connection
from backend.services import redis_cache as cache


def get_cards_info(conn: connection,
                        card_id : Optional[UUID|Sequence[UUID]]=None, 
                        limit : Annotated[int, Query(le=100)]=100,
                        offset: int = 0,
                        select_all : bool = True)-> Union[List[BaseCard] , BaseCard]:
    #if a list
    is_list = isinstance(card_id, list)
    cached_key = f"card:{card_id}:{limit}:{offset}" if card_id else f"cards:{limit}:{offset}"
    cached_result = cache.get_from_cache(cached_key)
    if cached_result:
        return [BaseCard(**card) for card in cached_result]

    query = """ SELECT uc.card_name, r.rarity_name, s.set_name,s.set_code, uc.cmc, cv.oracle_text, s.released_at, s.digital, r.rarity_name
            FROM unique_cards_ref uc
            JOIN card_version cv ON uc.unique_card_id = cv.unique_card_id
            JOIN rarities_ref r ON cv.rarity_id = r.rarity_id
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
        serialized = [dict(card) for card in cards]
        #cache all cards
        cache.set_to_cache(cached_key, serialized)
        return [BaseCard(**c) for c in serialized]
    except Exception:
        raise
    

