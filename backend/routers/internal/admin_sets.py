from backend.models.sets import   NewSet, UpdatedSet
from fastapi import APIRouter
from backend.dependancies import cursorDep
from backend.database.database_utilis import execute_insert_query, execute_delete_query, create_delete_query
from psycopg2.extensions import connection
from uuid import UUID

sets_router = APIRouter(
        prefix='/sets',
        tags=['admin-sets'], 
        responses={404:{'description':'Not found'}}
        
)

@sets_router.delete('/{set_id}')
async def delete_set(conn: cursorDep,
                    set_id : UUID):
    query=create_delete_query('sets', ['set_id = %s'])
    print(query)
    try:
        return execute_delete_query(conn, query, (str(set_id),), execute_many=False)
    except Exception:
        conn.rollback()
        raise

@sets_router.post('/')
async def add_set(new_set : NewSet, conn: cursorDep):
    query = "INSERT INTO joined_set (set_id, set_name, set_code, set_type, nonfoil_only, foil_only,  released_at, digital, parent_set) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    data = new_set.model_dump()
    values = tuple(v for _, v in data.items())
    try:
        return execute_insert_query(conn, query, values)
    except Exception:
        raise

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

@sets_router.put('/{set_id}')
async def update_set(conn: cursorDep,
                    set_id  : UUID, 
                    update_set : UpdatedSet):
    return put_set(conn, set_id, update_set)