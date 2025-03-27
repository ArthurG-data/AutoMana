from fastapi import APIRouter,  HTTPException
from backend.dependancies import cursorDep
from backend.models.collections import CreateCollection, PublicCollection, UpdateCollection
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_insert_query, execute_select_query, execute_delete_query, execute_update_query


import logging

logging.basicConfig(level=logging.INFO)

router = APIRouter(
    prefix='/collections',
    tags=['collection'],
    responses={404:{'description':'Not found'}}
)



def create_collection(created_user : CreateCollection, connection : connection )->dict:
    query = "INSERT INTO collections (collection_name, user_id) VALUES (%s, %s)  RETURNING collection_id"
    try:
        ids = execute_insert_query(connection, query,  (created_user.collection_name, created_user.user_id), unique_id='collection_id')
        return{'message' : 'collection successfuly created', 'ids' : ids}
    except Exception:
        raise

   
def collect_collection(collection_id : str, connection : connection) -> dict:
    query = """ SELECT u.username, c.collection_name, c.is_active FROM collections c JOIN users u ON c.user_id = u.unique_id WHERE c.collection_id = %s """

    try:
        return execute_select_query(connection, query, (collection_id,), select_all=False)
    except Exception:
        raise


def update_collection(collection_id : str, updated_collection : UpdateCollection , conn : connection)->dict:
    update_fields = {k: v for k, v in updated_collection.model_dump(exclude_unset=True).items()}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    query = "UPDATE collections SET " + ", ".join(f"{k} = %s" for k in update_fields.keys()) + " WHERE collection_id = %s RETURNING collection_id"
    values = tuple(update_fields.values()) + (collection_id,)
    try:
        execute_update_query(conn, query, values)
        return {'message' : 'collection data updated', 'ids': collection_id}
    except Exception:
        raise

def delete_collection( collection_id : str, connection : connection):
    query = "DELETE FROM collections WHERE collection_id = %s"
    try:
        execute_delete_query(connection, query, (collection_id,))
        return {'message' : 'collection deleted', 'id' : collection_id}
    except Exception:
        raise
    
@router.post('/')
async def add_collection(created_user : CreateCollection, connection : cursorDep )->dict:
    return create_collection(created_user, connection)

@router.delete('/{collection_id}')
async def remove_collection(collection_id : str, connection : cursorDep):
    return delete_collection(collection_id, connection)


@router.get('/{collection_id}', response_model=PublicCollection)
async def get_collection(collection_id : str, conn : cursorDep):
    return collect_collection(collection_id, conn)

@router.put('/{collection_id}')
async def change_collection(collection_id : str, updated_collection : UpdateCollection , conn : cursorDep):
    return update_collection(collection_id, updated_collection, conn)
    