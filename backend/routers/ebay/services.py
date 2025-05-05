from psycopg2.extensions import connection
from backend.routers.ebay.models import TokenInDb
from backend.routers.ebay.models import InputEbaySettings
from psycopg2.extensions import connection
from uuid import UUID
from typing import List
from backend.database.database_utilis import exception_handler

from backend.routers.ebay import queries

def save_refresh_token(conn: connection, new_refresh : TokenInDb):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.insert_token_query, (new_refresh.user_id, new_refresh.refresh_token, new_refresh.aquired_on, new_refresh.expires_on, new_refresh.token_type))          
    except Exception as e:
        exception_handler(e)
    
def register_ebay_user(dev_id : UUID , conn : connection, user_id : UUID):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.register_user_query,(user_id, dev_id,))
            conn.commit()
    except Exception as e:
        exception_handler(e)

def register_app(conn: connection, input:InputEbaySettings):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.register_app_query,(input.app_id, input.redirect_uri, input.response_type, input.hash_secret, ))
    except Exception as e:
        exception_handler(e)

def register_scope(conn: connection, scopes: str):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.register_scope_query, (scopes,))
            conn.commit()
    except Exception as e:
        exception_handler(e)

def assign_scope(conn: connection, scope : str):
    try:
        with conn.cursor() as cursor:
            cursor.executemany(queries.assign_scope_query, (scope,))
    except Exception as e:
        exception_handler(e)

def assign_app(conn : connection, scope : str, ebay_id :str):
    try:
        with conn.cursor() as cursor:
            cursor.executemany(queries.assign_user_app_query (ebay_id, scope))
    except Exception as e:
        exception_handler(e)

