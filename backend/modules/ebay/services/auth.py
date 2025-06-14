
import urllib, httpx
from pydantic import  HttpUrl
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from backend.database.database_utilis import execute_insert_query, execute_select_query
from backend.modules.ebay.models.auth import  AuthHeader, AuthData, ExangeRefreshData, TokenRequestData, TokenResponse
from backend.modules.ebay.queries import auth, app
from backend.models.settings import EbaySettings
from psycopg2.extensions import connection
from backend.database.database_utilis import exception_handler
from uuid import UUID,uuid4


def save_refresh_token(conn: connection, new_refresh : TokenResponse):
    try:
        with conn.cursor() as cursor:
            cursor.execute(auth.insert_token_query, (new_refresh.user_id, new_refresh.refresh_token, new_refresh.aquired_on, new_refresh.expires_on, new_refresh.token_type))          
    except Exception as e:
        exception_handler(e)

def set_ebay_settings(conn: connection, user : UUID, app_id : str)->EbaySettings:
    #to be implemented latter once in AWS
    try:
        with conn.cursor() as cursor:
            cursor.execute(auth.get_info_login, (user,app_id,))
            infos = cursor.fetchone()
            cursor.execute(app.get_scopes_app, (app_id, ))
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
    #add the params state with the request_id, but better to store a encrypted value, store the query and check if it exists when received
    print('Logging Into the Ebay App...')
    settings : EbaySettings = set_ebay_settings(conn, user, app_id)
    print(settings)
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
    except Exception as e:
        exception_handler(e)
    finally:
        return res
    

async def exange_refresh_token(conn : connection, refresh_token : str, user_id : UUID, app_id : str):
    settings : EbaySettings = set_ebay_settings(conn, user_id, app_id)
    headers = AuthHeader(app_id=app_id,secret=settings.secret ).to_header()
    data = ExangeRefreshData(token=refresh_token, scope=settings.scope).to_data()
    return await do_request_auth_ebay(headers, data)
   
    
async def save_refresh_token(conn : connection, token : TokenResponse, app_id : str, user_id : UUID):
    try:
        with conn.cursor() as cursor:
            cursor.execute(auth.insert_token_query, (app_id, token.refresh_token, token.acquired_on, token.expires_on,  token.token_type, user_id,))
            conn.commit()
            return {'message' : 'refresh token added'}
    except Exception as e:
        exception_handler(e)

def log_auth_request(conn : connection, request_id: UUID, session_id : UUID, request : HttpUrl, app_id)->UUID:
    try:

        request_id = execute_insert_query(conn, auth.register_oauth_request, (request_id, session_id, request,app_id,))
        if request_id:
            return request_id
    except Exception as e:
        raise e     
    
def check_auth_request(conn : connection, request_id : UUID) :
    try:
        row = execute_select_query(conn,auth.get_valid_oauth_request, (request_id,), select_all=False)
        session_id = row.get('session_id')
        app_id = row.get('app_id')
        if session_id and app_id:
            return session_id, app_id
        else:
            raise HTTPException(status_code=400, detail='message : Request invalid')
    except Exception as e:
        raise e

