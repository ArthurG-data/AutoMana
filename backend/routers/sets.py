from backend.models.sets import  SetwCount, NewSet, UpdatedSet
from fastapi import APIRouter, Query
from backend.dependancies import cursorDep
from backend.database.database_utilis import get_rows, delete_rows, execute_insert_query, execute_update_query
from typing import List,  Optional, Sequence, Annotated
from psycopg2.extensions import connection
from uuid import UUID

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

def post_set(conn : connection, new_set : NewSet):
    query = """ WITH
                ins_foil_ref AS ( 
                INSERT INTO foil_status_ref (foil_status_desc)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING foil_status_id
                ),
                get_foil_ref AS (
                SELECT foil_status_id FROM ins_foil_ref 
                UNION
                SELECT foil_status_id FROM foil_status_ref WHERE foil_status_desc = %s
                ),
                ins_set_type AS (
                INSERT INTO set_type_list_ref (set_type)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING set_type_id
                ),
                get_set_type AS (
                SELECT set_type_id FROM ins_set_type
                UNION
                SELECT set_type_id FROM set_type_list_ref WHERE set_type = %s
                ),
                get_parent_set AS (
                SELECT set_id FROM sets WHERE set_name = %s
                )
                INSERT INTO sets (set_name, set_code, set_type_id, released_at,digital,  foil_status_id, parent_set)
                SELECT %s, %s, gst.set_type_id, %s,%s, gfr.foil_status_id, gps.set_id
                FROM get_foil_ref gfr
                JOIN get_set_type gst ON TRUE
                LEFT JOIN get_parent_set gps ON TRUE
                RETURNING set_id;
 """
    try:
        id = execute_insert_query(conn, query, (new_set.foil_status_id, new_set.foil_status_id, new_set.set_type, new_set.set_type))
        return new_set
    except Exception:
        raise
   
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


@router.post('/')
async def add_set(conn : cursorDep, new_set : NewSet):
    return post_set(conn, new_set)

def put_set(conn: connection, set_id : UUID, update_set : UpdatedSet):
    not_nul = [k for k,v in update_set.model_dump().items() if v != None]
    update_string = ', '.join([f'{update} = %s'for update in not_nul])
    query = """WITH """
    params = []
    if 'set_type' in not_nul:
        query +=  """ins_set_type AS (
                INSERT INTO set_type_list_ref (set_type)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING set_type_id
                ),
                get_set_type AS (
                SELECT set_type_id FROM ins_set_type
                UNION
                SELECT set_type_id FROM set_type_list_ref WHERE set_type = %s
                ),"""
    params.extend([update_set.set_type] * 2)
    if 'foil_status_id' in not_nul:
        query +=  """ins_foil_ref AS ( 
                INSERT INTO foil_status_ref (foil_status_desc)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING foil_status_id
                ),
                get_foil_ref AS (
                SELECT foil_status_id FROM ins_foil_ref 
                UNION
                SELECT foil_status_id FROM foil_status_ref WHERE foil_status_desc = %s
                ), """
    if 'parent_set' in not_nul:
         query += """get_parent_set AS (
                    SELECT set_id from sets
                    WHERE set_name = %s     
                    ),
                  """
    query += f" UPDATE sets SET ({update_string}) WHERE set_id = %s"
    params.extend([update_set.foil_status_id] * 2)
    for entry in not_nul:
        if entry not in ['foil_status_id', 'set_type']:
            params.append(getattr(update_set, entry, None))
    params.append(set_id)
    try:
        execute_insert_query(conn, query, params)
    except Exception:
        raise

@router.put('/{set_id}')
async def update_set(conn: cursorDep,
                    set_id  : UUID, 
                    update_set : UpdatedSet):
    return put_set(conn, set_id, update_set)