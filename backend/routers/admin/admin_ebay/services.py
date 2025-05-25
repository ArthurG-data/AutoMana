from psycopg2.extensions import connection
from typing import Optional
from backend.routers.admin.admin_ebay import queries
from backend.database.database_utilis import exception_handler

def register_scope(conn: connection, scopes: str, scope_description : Optional[str]):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.register_scope_query, (scopes, scope_description, ))
            conn.commit()
    except Exception as e:
        exception_handler(e)
