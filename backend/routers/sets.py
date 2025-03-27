from backend.models.sets import  SetwCount
from fastapi import APIRouter, Query
from backend.dependancies import cursorDep
from backend.database.database_utilis import get_rows, delete_rows
from typing import List,  Optional, Sequence, Annotated


router = APIRouter(
        prefix='/sets',
        tags=['sets'], 
        responses={404:{'description':'Not found'}}
        
)

def get_query_creator(is_list : bool, values : Optional[Sequence[str]|str]=None) -> str:
    query = """ SELECT s.set_id, s.set_name, s.set_code, stl.set_type,  COUNT(cv.set_id) AS card_count,s.released_at, s.digital
            FROM sets s
            JOIN set_type_list stl ON s.set_type_id = stl.set_type_id
            JOIN card_version cv ON cv.set_id = s.set_id """
    if is_list:
        query += "WHERE s.set_id = ANY(%s) LIMIT %s OFFSET %s;"
    elif values :
        query += "WHERE s.set_id = %s "
    query += " GROUP BY s.set_id,  stl.set_type, s.released_at "
    if is_list or not values:
        query += "LIMIT %s OFFSET %s "
    query += ';'
    return query


@router.get('/{set_id}', response_model=SetwCount)
async def get_set(connection: cursorDep, set_id : str):
    return  get_rows(connection, get_query_creator, set_id, select_all=False )

@router.get('/', response_model=List[SetwCount])
async def get_sets(connection: cursorDep,
                    limit : Annotated[int, Query(le=100)]=100,
                    offset: int =0,
                    set_id : Annotated[List[str],Query(title='Optional set_is')]=None):
    return  get_rows(connection, get_query_creator, set_id, limit=limit, offset=offset, select_all=True)

@router.delete('/{set_id}')
async def delete_set(connection: cursorDep,
                    set_id : str):
    return delete_rows(connection, get_query_creator, values=set_id)

