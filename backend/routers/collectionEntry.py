from fastapi import APIRouter, Depends, Response, HTTPException
from backend.models.collections import PublicCollectionEntry, NewCollectionEntry, UpdateCollectionEntry
from backend.database.database_utilis import execute_insert_query, execute_delete_query,execute_select_query,execute_update_query
from psycopg2.extensions import connection
from typing import Annotated
from backend.dependancies import cursorDep
from uuid import UUID

router =  APIRouter(
    prefix = '/inventory',
    tags = ['inventory'],

)



@router.delete('/{entry_id}')
async def delete_entry(conn : cursorDep, entry_id : UUID):
    query = """ DELETE FROM  collectionItems
                WHERE item_id = %s
            """
    try:
            return  execute_delete_query(conn, query, (entry_id,))
    except Exception:
            raise 
    
@router.get('/{entry_id}', response_model=PublicCollectionEntry)
async def get_entry(conn : cursorDep, entry_id : UUID):
    query = """ SELECT c.item_id, c.collection_id,  c.unique_card_id, c.is_foil, c.purchase_date,c.purchase_price, rc.condition_description AS condition
                FROM collectionItems c
                JOIN Ref_Condition rc ON rc.condition_code = c.condition
                WHERE item_id = %s
            """
    try:
        return  execute_select_query(conn, query, (entry_id,), select_all=False)
    except Exception:
            raise 
        
    
@router.put('/{entry_id}')
async def update_entry(conn : cursorDep, entry_id : UUID, updated : UpdateCollectionEntry):
    update_fields = {k: v for k, v in updated.model_dump(exclude_unset=True).items()}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    query = "UPDATE collectionItems SET " + ", ".join(f"{k} = %s" for k in update_fields.keys()) + " WHERE item_id = %s "
    values = tuple(update_fields.values()) + (entry_id,)
    print(query, values)
    try:
        return execute_update_query(conn, query, values)
    except Exception:
        raise

@router.post('/')
async def add_entry( conn : cursorDep, new_entry :NewCollectionEntry):
    query = """  INSERT INTO collectionItems ( collection_id, unique_card_id, is_foil, purchase_date,  purchase_price, condition)
            SELECT %s, %s, %s, %s, %s, condition_code
            FROM Ref_Condition
            Where condition_description = %s 
            RETURNING item_id
            """

    try:
        values = (
            new_entry.collection_id, 
            new_entry.unique_card_id, 
            new_entry.is_foil, 
            new_entry.purchase_date, 
            new_entry.purchase_price, 
            new_entry.condition.value
        )
        cursor = conn.cursor()

        cursor.execute(query, values)
        conn.commit()
        row = cursor.fetchone()
        return {'status' : 200, 'new_id' : row}
    except Exception as e:
        conn.rollback()
        return {'status' : 400, 'message': str(e)}
    finally:
        cursor.close()

   
