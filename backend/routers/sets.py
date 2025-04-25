from fastapi import APIRouter, Query, Response, HTTPException
from typing import List,  Optional, Sequence, Annotated
from uuid import UUID
from backend.dependancies import cursorDep
from backend.database.database_utilis import get_rows, create_select_query, execute_select_query
from backend.models.sets import  SetwCount
from psycopg2.extensions import connection


router = APIRouter(
        prefix='/sets',
        tags=['sets'], 
        responses={404:{'description':'Not found'}}
        
)


def create_value(values, is_list : bool, limit : Optional[int]=None, offset : Optional[int]=None):
    if is_list:
        values = ((values ), limit , offset)
    elif values:
        values = (values ,)
    else:
        values = (limit , offset)
    return values


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

@router.get('/{set_id}', response_model=SetwCount)
async def get_set(set_id : UUID, connection: cursorDep):
    return  retrieve_set(connection, ids=set_id, select_all=False )

@router.get('/', response_model=List[SetwCount])
async def get_sets(connection: cursorDep,
                    limit : Annotated[int, Query(le=100)]=100,
                    offset: int =0,
                    set_ids : Annotated[List[str],Query(title='Optional set_is')]=None):
     return  retrieve_set(connection, ids=set_ids,  limit=limit, offset=offset, select_all=True)

