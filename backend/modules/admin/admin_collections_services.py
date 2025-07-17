
from psycopg2.extensions import connection
from backend.database.database_utilis import  execute_select_query, execute_delete_query
from typing import Optional


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
    

