from fastapi import APIRouter,  HTTPException, Depends, Response
from backend.models.users import UserInDB
from backend.dependancies import cursorDep
from backend.models.collections import CreateCollection, PublicCollection, UpdateCollection
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_insert_query, execute_select_query, execute_delete_query, execute_update_query
from typing import List, Optional
from backend.authentification import get_current_user, get_current_active_user, check_token_validity


router = APIRouter(
    prefix='/collections',
    tags=['collection'],
    dependencies=[Depends(check_token_validity)],
    responses={404:{'description':'Not found'}}
)

def create_collection(created_collection : CreateCollection, connection : connection, user : UserInDB = Depends(get_current_active_user))->dict:
    query = "INSERT INTO collections (collection_name, user_id) VALUES (%s, %s)  RETURNING collection_id"
    try:
        ids = execute_insert_query(connection, query,  (created_collection.collection_name, user.unique_id), unique_id='collection_id')
        return{'message' : 'collection successfuly created', 'ids' : ids}
    except Exception:
        raise

   
def collect_collection(collection_id : Optional[str] , connection : connection, user : UserInDB = Depends(get_current_active_user) )-> dict:

    query = """ SELECT u.username, c.collection_name, c.is_active 
                FROM collections c JOIN users u 
                ON c.user_id = u.unique_id 
                WHERE c.user_id = %s """
    values = (user.unique_id,)
    if collection_id :
        query.join('AND c.collection_id = %s')
        values= (user.unique_id, collection_id,)

    try:
        return execute_select_query(connection, query, values=values, select_all=False)
    except Exception:
        raise


def update_collection(collection_id : str, updated_collection : UpdateCollection , conn : connection, user : UserInDB = Depends(get_current_active_user))->dict:
    update_fields = {k: v for k, v in updated_collection.model_dump(exclude_unset=True).items()}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    query = "UPDATE collections SET " + ", ".join(f"{k} = %s" for k in update_fields.keys()) + " WHERE collection_id = %s AND user_id = %s"
    values = tuple(update_fields.values()) + (collection_id,user.unique_id)
    try:
        execute_update_query(conn, query, values)
        return Response(status_code=204)
    except Exception:
        raise

def delete_collection( collection_id : str, connection : connection, user : UserInDB = Depends(get_current_active_user)):
    query = "DELETE FROM collections WHERE collection_id = %s AND user_id = %s"
    try:
        execute_delete_query(connection, query, (collection_id,user.unique_id))
        return {'message' : 'collection deleted', 'id' : collection_id}
    except Exception:
        raise
    

@router.post('/')
async def add_collection(created_collection : CreateCollection, connection : cursorDep , current_user = Depends(get_current_user))->dict:
    return create_collection(created_collection, connection, current_user)

@router.delete('/{collection_id}', status_code=200)
async def remove_collection(collection_id : str, connection : cursorDep, current_user = Depends(get_current_user)):
    return delete_collection(collection_id, connection,  current_user)


@router.get('/{collection_id}', response_model=PublicCollection)
async def get_collection(collection_id : str, conn : cursorDep, current_user = Depends(get_current_user)) :
    return collect_collection(collection_id, conn, current_user)

@router.get('/', response_model=List[PublicCollection])
async def get_collection(conn : cursorDep, current_user = Depends(get_current_user)):
    return collect_collection(connextion = conn, user=current_user)

@router.put('/{collection_id}', status_code=204)
async def change_collection(collection_id : str, updated_collection : UpdateCollection , conn : cursorDep,  current_user = Depends(get_current_user)):
    return update_collection(collection_id, updated_collection, conn, current_user)
    