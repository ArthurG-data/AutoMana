from backend.modules.internal.sets.models import   NewSet, UpdatedSet, NewSets
from fastapi import APIRouter, Response, status, File, UploadFile, Depends
from backend.database.get_database import cursorDep
from backend.database.database_utilis import execute_delete_query, create_delete_query
from uuid import UUID
from backend.modules.internal.sets.utils import sets_from_json
from backend.modules.internal.sets.services import put_set, add_set,add_sets_bulk

sets_router = APIRouter(
        prefix='/sets',
        tags=['internal-sets'], 
        responses={404:{'description':'Not found'}}
        
)

@sets_router.delete('/{set_id}')
async def delete_set(conn: cursorDep,
                    set_id : UUID):
    query=create_delete_query('sets', ['set_id = %s'])
    try:
        return execute_delete_query(conn, query, (str(set_id),), execute_many=False)
    except Exception:
        conn.rollback()
        raise

@sets_router.post('/bulk', description='An endpoint to add multiple sets to the database')
async def insert_sets(conn : cursorDep,sets : NewSets):
    add_sets_bulk(sets, conn)
    return Response(status_code=status.HTTP_201_CREATED)

@sets_router.post('/', description='An endpoint to add a new set')
async def insert_set(new_set : NewSet, conn: cursorDep):
    add_set(new_set, conn)
    return Response(status_code=status.HTTP_201_CREATED)
  

@sets_router.post('/from_json')
async def insert_sets_from_file(conn : cursorDep, parsed_sets :NewSet=Depends(sets_from_json)):
    #while be bytes
    try:
        add_sets_bulk(parsed_sets, conn)
        return {'success'}
    except Exception as e:
        return [f"Error: {str(e)}"]


@sets_router.put('/{set_id}')
async def update_set(conn: cursorDep,
                    set_id  : UUID, 
                    update_set : UpdatedSet):
    return put_set(conn, set_id, update_set)