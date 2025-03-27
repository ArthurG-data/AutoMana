from fastapi import APIRouter, Depends, HTTPException
from backend.dependancies import cursorDep
from backend.models.collections import CreateCollection, PublicCollection, UpdateCollection
from psycopg2.extensions import connection
from typing import Annotated
from backend.database.get_database import get_connection, get_cursor

import logging

logging.basicConfig(level=logging.INFO)

router = APIRouter(
    prefix='/collections',
    tags=['collection'],
    responses={404:{'description':'Not found'}}
)

def create_collection(created_user : CreateCollection, connection : connection )->dict:
    query = "INSERT INTO collections (collection_name, user_id) VALUES (%s, %s)  RETURNING collection_id"
    with connection.cursor() as cursor:
        try:
            cursor.execute(query, (created_user.collection_name, created_user.user_id))
            connection.commit()
            row = cursor.fetchone()
            if row:
                return {'id' : str(row['collection_id'])}
            else:
                raise HTTPException(status_code=500, detail="Failed to retrieve collection ID")
            
                
        except Exception as e:
            return {'status' : 'error creating collection', 'message': str(e)}

def collect_collection(collection_id : str, connection : connection) -> dict:
    query = """ SELECT u.username, c.collection_name, c.is_active FROM collections c JOIN users u ON c.user_id = u.unique_id WHERE c.collection_id = %s """
    with connection.cursor() as cursor:
        try:
            cursor.execute(query, (collection_id,))
            row = cursor.fetchone()
            return row
    
        except Exception as e:
            return {'status' : 'error fetching collection', 'message': str(e)}

def update_collection(collection_id : str, updated_collection : UpdateCollection , conn : connection)->dict:
    update_fields = {k: v for k, v in updated_collection.model_dump(exclude_unset=True).items()}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    query = "UPDATE collections SET " + ", ".join(f"{k} = %s" for k in update_fields.keys()) + " WHERE collection_id = %s RETURNING collection_id"
    values = tuple(update_fields.values()) + (collection_id,)
    with conn.cursor() as cursor:
        cursor.execute(query, values)
        conn.commit()
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Collection not found")

    return {"message": "Collection updated successfully", "collection_id": collection_id}

def delete_collection( collection_id : str, connection : connection):
    query = "DELETE FROM collections WHERE collection_id = %s"
    with connection.cursor() as cursor:
        try:
            cursor.execute(query, (collection_id,))
            connection.commit()
            return {'message' : 'collection deleted', 'id' : collection_id}
    
        except Exception as e:
            return {'status' : 'error creating collection', 'message': str(e)}
   
    
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
    