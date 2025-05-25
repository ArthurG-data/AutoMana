from psycopg2.extensions import connection
from backend.routers.ebay.models import TokenResponse
from backend.routers.ebay.models import InputEbaySettings
from psycopg2.extensions import connection
from uuid import UUID
from pydantic import  HttpUrl
from fastapi import HTTPException
from backend.database.database_utilis import exception_handler
from backend.models.settings import EbaySettings
from backend.database.database_utilis import execute_insert_query, execute_select_query
from backend.routers.ebay import queries

def save_refresh_token(conn: connection, new_refresh : TokenResponse):
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

def register_app(conn: connection, input:InputEbaySettings, settings : EbaySettings):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.register_app_query,(input.app_id, input.redirect_uri, input.response_type, input.secret,input.secret, settings.secret_key))
            conn.commit()
    except Exception as e:
        exception_handler(e)

def assign_app(conn : connection, app_id : UUID, ebay_id :str):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.assign_user_app_query, (ebay_id, app_id,))
            conn.commit()
    except Exception as e:
        exception_handler(e)

def assign_scope(conn: connection, scope : str, app_id : str):
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.assign_scope_query, (app_id,scope,))
            conn.commit()
    except Exception as e:
        exception_handler(e)

def log_auth_request(conn : connection, request_id: UUID, session_id : UUID, request : HttpUrl, app_id)->UUID:
    try:

        request_id = execute_insert_query(conn, queries.register_oauth_request, (request_id, session_id, request,app_id,))
        if request_id:
            return request_id
    except Exception as e:
        raise e     
def check_auth_request(conn : connection, request_id : UUID) :
    try:
        row = execute_select_query(conn, queries.get_valid_oauth_request, (request_id,), select_all=False)
        session_id = row.get('session_id')
        app_id = row.get('app_id')
        if session_id and app_id:
            return session_id, app_id
        else:
            raise HTTPException(status_code=400, detail='message : Request invalid')
    except Exception as e:
        raise e
