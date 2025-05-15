from fastapi import HTTPException
from typing import List,  Optional, Sequence
from uuid import UUID
from backend.database.database_utilis import create_select_query, execute_select_query
from psycopg2.extensions import connection
from backend.routers.sets.utils import create_value


def retrieve_set( conn : connection, limit : Optional[int]=None, offset : Optional[int]=None, ids : Optional[Sequence[UUID]|UUID]=None, select_all : Optional[bool]=False) -> dict:
    conditions = None
    if isinstance(ids, List):
        conditions =  ["set_id IN %s "]
    elif isinstance(ids, UUID):
        conditions =  ["set_id = %s "]
    query = create_select_query('joined_set_materialized',conditions_list=conditions,limit=limit, offset=offset )
    values= create_value(ids, isinstance(ids, List), limit, offset)
    try:
        return execute_select_query(conn, query, values, execute_many=False, select_all=select_all)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))