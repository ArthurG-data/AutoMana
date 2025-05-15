from fastapi import APIRouter
from backend.database.get_database import cursorDep
from backend.routers.collections.models import PublicCollection
from psycopg2.extensions import connection
from backend.database.database_utilis import  execute_select_query, execute_delete_query
from typing import List, Optional
from psycopg2.extensions import connection

import logging

logging.basicConfig(level=logging.INFO)

collection_router = APIRouter(
    prefix='/collections',
    tags=['admin-collection'],
    responses={404:{'description':'Not found'}}
)

def collect_collection(collection_id : Optional[str] , connection : connection)-> dict:

    query = """ SELECT u.username, c.collection_name, c.is_active 
                FROM collections c JOIN users u 
                ON c.user_id = u.unique_id 
                WHERE c.user_id = %s """
    if collection_id :
        query.join('AND c.collection_id = %s')
        values= (collection_id,)
    try:
        return execute_select_query(connection, query, values=values, select_all=True)
    except Exception:
        raise

def delete_collection( collection_id : str, connection : connection, ):
    query = "DELETE FROM collections WHERE collection_id = %s "
    try:
        execute_delete_query(connection, query, (collection_id,))
        return {'message' : 'collection deleted', 'id' : collection_id}
    except Exception:
        raise
    

@collection_router.delete('/{collection_id}')
async def remove_collection(collection_id : str, connection : cursorDep):
    return delete_collection(collection_id, connection)


@collection_router.get('/{collection_id}', response_model=PublicCollection)
async def get_collection(collection_id : str, conn : cursorDep):
    return collect_collection(collection_id, conn)

@collection_router.get('/', response_model=List[PublicCollection])
async def get_collection(conn : cursorDep):
    return collect_collection(conn)

