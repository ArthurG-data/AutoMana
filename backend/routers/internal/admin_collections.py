from fastapi import APIRouter,  HTTPException, Depends
from typing import Annotated
from backend.models.users import UserInDB
from backend.dependancies import cursorDep
from backend.models.collections import CreateCollection, PublicCollection, UpdateCollection
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_insert_query, execute_select_query, execute_delete_query, execute_update_query
from typing import List, Optional
from backend.authentification import get_current_user, get_hash_password, get_current_active_user, check_token_validity
import logging

logging.basicConfig(level=logging.INFO)

collection_router = APIRouter(
    prefix='/collections',
    tags=['admin-collection'],
    dependencies=[Depends(check_token_validity)],
    responses={404:{'description':'Not found'}}
)



@collection_router.post('/')
async def add_collection(created_collection : CreateCollection, connection : cursorDep , current_user = Depends(get_current_user))->dict:
    
    return create_collection(created_collection, connection)

@collection_router.delete('/{collection_id}')
async def remove_collection(collection_id : str, connection : cursorDep):
    return delete_collection(collection_id, connection)


@collection_router.get('/{collection_id}', response_model=PublicCollection)
async def get_collection(collection_id : str, conn : cursorDep):
    return collect_collection(collection_id, conn)

@collection_router.get('/', response_model=List[PublicCollection])
async def get_collection(conn : cursorDep):
    return collect_collection(conn)

@collection_router.put('/{collection_id}')
async def change_collection(collection_id : str, updated_collection : UpdateCollection , conn : cursorDep):
    return update_collection(collection_id, updated_collection, conn)