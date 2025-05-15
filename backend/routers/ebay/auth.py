
import urllib,  base64, httpx
from fastapi.responses import RedirectResponse
from backend.routers.ebay.models import  AuthHeader, AuthData, ExangeRefreshData, TokenRequestData
from backend.models.settings import EbaySettings
from psycopg2.extensions import connection
from backend.routers.ebay import queries
from backend.database.database_utilis import exception_handler
from uuid import UUID
from backend.routers.ebay.models import TokenResponse

def set_ebay_settings(conn: connection, user : UUID, app_id : str)->EbaySettings:
    #to be implemented latter once in AWS
   
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.get_info_login, (user,app_id,))
            infos = cursor.fetchone()
            cursor.execute(queries.get_scopes_app, (app_id, ))
            scopes = cursor.fetchall()
            scopes = [row['scope_description'].strip('"') for row in scopes]
            return EbaySettings(app_id=infos['app_id'], 
                        response_type=infos['response_type'], 
                        redirect_uri=infos['redirect_uri'], 
                        scope=scopes, 
                        secret=infos['decrypted_secret'])

    except Exception as e:
        exception_handler(e)
  
    

def login_ebay(conn : connection, user : UUID, app_id : str):
    #to be implemented latter once in AWS
    #add the params state with the request_id
    print('Logging Into the Ebay App...')
    settings : EbaySettings = set_ebay_settings(conn, user, app_id)
    params = {
        "client_id":settings.app_id,
        "response_type": settings.response_type,
        "redirect_uri": settings.redirect_uri,
        "scope": " ".join(settings.scope),
        "secret" : settings.secret,
        "state" : "test_of state"
    }

    auth_url = f"https://auth.ebay.com/oauth2/authorize?{urllib.parse.urlencode(params)}"
    print(auth_url)
    return RedirectResponse(url=auth_url)



async def  do_request_auth_ebay(headers : AuthHeader, data : TokenRequestData)->TokenResponse :
    async with httpx.AsyncClient() as client:
        res = await client.post(url='https://api.ebay.com/identity/v1/oauth2/token', headers=headers, data =data)
        res.raise_for_status()
        token_response = res.json()
        print(token_response)
    return TokenResponse(**token_response)


async def exange_auth(conn : connection, code : str, user_id : UUID, app_id='to implement'):
    
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
            cursor.execute(queries.insert_token_query, (app_id, token.refresh_token, token.acquired_on, token.expires_on,  token.token_type, user_id,))
            conn.commit()
            return {'message' : 'refresh token added'}
    except Exception as e:
        exception_handler(e)