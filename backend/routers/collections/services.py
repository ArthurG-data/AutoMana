from fastapi import   HTTPException, Depends, Response
from backend.routers.users.models import UserInDB
from psycopg2.extensions import connection
from backend.routers.collections.models import CreateCollection, UpdateCollection
from backend.routers.auth.depndancies import currentActiveUser
from backend.database.database_utilis import execute_insert_query, execute_select_query, execute_delete_query, execute_update_query
from typing import  Optional

def create_collection(created_collection : CreateCollection, connection : connection, user : UserInDB = currentActiveUser)->dict:
    query = "INSERT INTO collections (collection_name, user_id) VALUES (%s, %s)  RETURNING collection_id"
    try:
        ids = execute_insert_query(connection, query,  (created_collection.collection_name, user.unique_id), unique_id='collection_id')
        return{'message' : 'collection successfuly created', 'ids' : ids}
    except Exception:
        raise
 
def collect_collection(collection_id : Optional[str] , connection : connection, user : UserInDB = currentActiveUser )-> dict:

    query = """ SELECT u.username, c.collection_name, c.is_active 
                FROM collections c JOIN users u 
                ON c.user_id = u.unique_id 
                WHERE c.user_id = %s AND c.is_active = True"""
    values = (user.unique_id,)
    if collection_id:
        query.join('AND c.collection_id = %s')
        values= (user.unique_id, collection_id,)

    try:
        return execute_select_query(connection, query, values=values, select_all=True)
    except Exception:
        raise

def update_collection(collection_id : str, updated_collection : UpdateCollection , conn : connection, user : currentActiveUser)->dict:
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

def delete_collection( collection_id : str, connection : connection, user :currentActiveUser):
    query = "UPDATE collections set is_active = False WHERE collection_id = %s AND user_id = %s"
    try:
        execute_delete_query(connection, query, (collection_id,user.unique_id))
        return {'message' : 'collection deleted', 'id' : collection_id}
    except Exception:
        raise
    
