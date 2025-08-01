
import urllib, httpx
from pydantic import  HttpUrl
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from backend.database.database_utilis import execute_insert_query, execute_select_query
from backend.modules.ebay.models.auth import  AuthHeader, AuthData, ExangeRefreshData, TokenRequestData, TokenResponse
from backend.repositories.app_integration.ebay import app_queries
from backend.repositories.app_integration.ebay import auth_queries
from backend.schemas.settings import EbaySettings
from psycopg2.extensions import connection
from backend.database.database_utilis import exception_handler
from uuid import UUID,uuid4
from backend.database.get_database import cursorDep
from backend.modules.auth.dependancies import currentActiveUser


def set_ebay_settings(conn: connection, user : UUID, app_id : str)->EbaySettings:
    #to be implemented latter once in AWS

    with conn.cursor() as cursor:
            cursor.execute(auth_queries.get_info_login, (user,app_id,))
            infos = cursor.fetchone()
    try:
        with conn.cursor() as cursor:
            cursor.execute(auth_queries.get_info_login, (user,app_id,))
            infos = cursor.fetchone()
            cursor.execute(app_queries.get_scopes_app, (app_id, ))
            scopes = cursor.fetchall()
            scopes = [row['scope_url']for row in scopes]
            return EbaySettings(app_id=infos['app_id'], 
                        response_type=infos['response_type'], 
                        redirect_uri=infos['redirect_uri'], 
                        scope=scopes, 
                        secret=infos['decrypted_secret'])
    except Exception as e:
        exception_handler(e)
  

def login_ebay(conn : connection, user : UUID, app_id : str, session_id :UUID):

    print('Logging Into the Ebay App...')
    settings : EbaySettings = set_ebay_settings(conn, user, app_id)
    request_id = uuid4()
    params = {
        "client_id":settings.app_id,
        "response_type": settings.response_type,
        "redirect_uri": settings.redirect_uri,
        "scope": " ".join(settings.scope),
        "secret" : settings.secret,
        "state" : request_id
    }
    auth_url = f"https://auth.ebay.com/oauth2/authorize?{urllib.parse.urlencode(params)}"
    print('url:',auth_url)
    try:
        log_auth_request(conn,request_id,  session_id, auth_url, app_id)
    except Exception as e:
        raise HTTPException(status_code=400,detail= f'{e}')
    return RedirectResponse(url=auth_url)


async def  do_request_auth_ebay(headers : AuthHeader, data : TokenRequestData)->TokenResponse :
    async with httpx.AsyncClient() as client:
        res = await client.post(url='https://api.ebay.com/identity/v1/oauth2/token', headers=headers, data =data)
        res.raise_for_status()
        token_response = res.json()
    return TokenResponse(**token_response)


async def exange_auth(conn : connection, code : str, user_id : UUID, app_id : UUID):
    settings : EbaySettings = set_ebay_settings(conn, user_id, app_id)
    headers = AuthHeader(app_id=app_id,secret=settings.secret ).to_header()
    data = AuthData(code = code, redirect_uri = settings.redirect_uri).to_data()
    res : TokenResponse = await do_request_auth_ebay(headers, data)  
    try:
        await save_refresh_token(conn,res, app_id, user_id)
        await save_access_token(conn, res, app_id, user_id)
    except Exception as e:
        exception_handler(e)
    finally:
        return res
    

async def exange_refresh_token(conn : connection, refresh_token : str, user_id : UUID, app_id : str):
    settings : EbaySettings = set_ebay_settings(conn, user_id, app_id)
    headers = AuthHeader(app_id=app_id,secret=settings.secret).to_header()
    data = ExangeRefreshData(token=refresh_token, scope=settings.scope).to_data()
    return await do_request_auth_ebay(headers, data)
   

    
async def save_refresh_token(conn : connection, token : TokenResponse, app_id : str, user_id : UUID):
    try:
        with conn.cursor() as cursor:
            cursor.execute(auth_queries.assign_refresh_ebay_query, ( app_id,app_id, token.refresh_token, token.acquired_on, token.refresh_expires_on,  'refresh_token', user_id,))
            conn.commit()
            return {'message' : 'refresh token added'}
    except Exception as e:
        exception_handler(e)

async def save_access_token(conn : connection, token : TokenResponse, app_id : str, user_id : UUID):
    try:
        with conn.cursor() as cursor:
            cursor.execute(auth_queries.assign_access_ebay_query, ( app_id,app_id, token.access_token, token.acquired_on, token.expires_on,  'access_token', user_id,))
            conn.commit()
            return {'message' : 'refresh token added'}
    except Exception as e:
        exception_handler(e)

def log_auth_request(conn : connection, request_id: UUID, session_id : UUID, request : HttpUrl, app_id)->UUID:
    try:

        request_id = execute_insert_query(conn, auth_queries.register_oauth_request, (request_id, session_id, request,app_id,))
        if request_id:
            return request_id
    except Exception as e:
        raise e     
    
def check_auth_request(conn : connection, request_id : UUID) :
    try:
        row = execute_select_query(conn,auth_queries.get_valid_oauth_request, (request_id,), select_all=False)
        session_id = row.get('session_id')
        app_id = row.get('app_id')
        if session_id and app_id:
            return session_id, app_id
        else:
            raise HTTPException(status_code=400, detail='message : Request invalid')
    except Exception as e:
        raise e


async def check_app_access(conn : connection, user_id: UUID, app_id :str)->bool:
    #check if user is associated to the app
    query = """
            SELECT EXISTS (
                SELECT 1
                FROM ebay_app
                WHERE user_id = %s AND app_id = %s
            );
            """
    return execute_select_query(conn, query, (user_id,app_id), select_all=False)

async def get_access_from_refresh(app_id : str, user_id : UUID, conn: connection):
    # check if valide session
    query_2 = """ SELECT token
                FROM ebay_tokens
                WHERE app_id = %s AND used = false AND token_type= 'refresh_token';
            """
    #check if access token is valid wirh session
    try:
        row = execute_select_query(conn, query_2, (app_id,),select_all=False)
        refresh_token = row.get('token')
    except Exception as e:
        return str(e)
    try:
        access_token = await exange_refresh_token(conn, refresh_token,user_id , app_id)
    except Exception as e:
        return {'error in exange:' : str(e)}
    return access_token

async def get_valid_access_token(user_id : UUID,app_id : UUID, conn: connection)->str:
    query_1 = """ SELECT token
                FROM ebay_tokens
                WHERE app_id = %s
                AND expires_on > now()
                AND used = false
                AND token_type = 'access_token'
                ORDER BY acquired_on DESC
                LIMIT 1;
            """
    if await check_app_access(conn, user_id, app_id):
        #if valid , get access token
        row = execute_select_query(conn, query_1, (app_id,),select_all=False)
    if not row:
        token = await get_access_from_refresh(app_id, user_id, conn)
    else:
        token = row.get("token")
    #here check if a toke has beer returned
  
    return token
   
async def check_validity(app_id : str, user : currentActiveUser, conn : cursorDep)->str:
    try:
        token : str = await get_valid_access_token(user.unique_id, app_id,conn)
        return token
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")


   
