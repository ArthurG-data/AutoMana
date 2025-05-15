from uuid import UUID
from fastapi import Query
from typing import Annotated, Union, Sequence, Optional, List
from backend.routers.cards.models import BaseCard
from backend.database.database_utilis import  execute_select_query
from psycopg2.extensions import connection

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
    

