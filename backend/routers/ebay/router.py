
from fastapi import APIRouter,Response, Request, HTTPException, Query
from backend.routers.ebay import queries
from backend.database.get_database import cursorDep
from backend.routers.ebay.models import TokenResponse, InputEbaySettings
from backend.shared.dependancies import currentActiveUser, currentActiveSession
from backend.routers.ebay.auth import login_ebay, exange_auth, exange_refresh_token
from backend.routers.ebay.services import register_ebay_user,assign_scope, register_app, assign_app, check_auth_request
from uuid import UUID
from backend.routers.auth.services import get_active_session,get_info_session


router = APIRouter(
)


@router.post('/dev/register', description='Add a ebay_user to the database that will be linked to the current user', tags=['dev'])
async def regist_user(conn: cursorDep, current_user : currentActiveUser, dev_id : UUID):
    register_ebay_user(dev_id, conn, current_user.unique_id)
    return Response(status_code=200, content='Dev added')

@router.post('/app/login')
async def login(conn : cursorDep, user : currentActiveUser,session_id: currentActiveSession, app_id : str):
     return login_ebay(conn, user.unique_id, app_id, session_id)
   

@router.post('/app/{app_id}/scopes', description='add a scope to an app', tags=['app'])
async def add_user_scope(conn : cursorDep, scope : str, app_id : str):
   
    try:
        assign_scope(conn,  app_id, scope)
    except Exception as e:
        return {'message' : 'Could not assign scope to app', 'error' : f'{e}'}
    return Response(status_code=200)

@router.post('/app', description='add an app to the database', tags=['app'])
async def regist_app(conn: cursorDep, input : InputEbaySettings ):
    register_app(conn, input)
    return Response(status_code=200, content='app added')

@router.post('/app/{app_id}/{ebay_id}', tags=['app'])
async def assign_user_app(conn: cursorDep, app_id : str, ebay_id : UUID):
    #add auhoixation later
    assign_app(conn, app_id, ebay_id)
    return Response(status_code=200, content='User assigned to app')





@router.get("/token", response_model=TokenResponse)
async def exange_auth_token(conn : cursorDep,  request : Request):
    code = request.query_params.get('code')
    request_id = request.query_params.get("state")
    #next from the request_id, get the session
    try:
        session_id, app_id = check_auth_request(conn, request_id)
        user = await get_info_session(conn, session_id)
        user = user.get('user_id')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot confirm request info: {e}")
    #next from the session get user and app
    if code and request_id:
        return await exange_auth(conn, user_id=user, code=code, app_id=app_id)
    return {'error' : 'authorization not found'}


@router.post('/auth/exange_token')
async def do_exange_refresh_token(conn : cursorDep, user : currentActiveUser, app_id  :str):
    #check if the has a non expired token for the app
    try:
        with conn.cursor() as cursor:
            cursor.execute(queries.get_refresh_token_query, (user.unique_id, app_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail='App not available for this user')
            return await exange_refresh_token(conn, row.get('refresh_token'), user.unique_id, app_id)
    except Exception as e:
        raise
            

@router.get('/refresh')
async def do_exange_token():
    pass

@router.get('/app/listings')

@router.get('/app/listing/{listing_id}')
async def getActiveListing():
    raise HTTPException(status_code=400, detail='Not implemented')

from backend.routers.ebay.ebay_api import doPostTradingRequest, create_xml_body, HeaderApi
from typing import Annotated

@router.get("/ebay/active-listings/")
async def do_api_call(token, limit : Annotated[int , Query(gt=1, le=50)] , offset :  Annotated[int , Query(gt=1,)]):
    header = HeaderApi('00', 967,'GetMyeBaySelling', token)
    xml_body = create_xml_body('GetMyeBaySelling', limit, offset)
    try:
        return await doPostTradingRequest(xml_body,header)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f'xould not get all active listings: {e}')

