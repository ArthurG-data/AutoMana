from fastapi import HTTPException, APIRouter, Request
from backend.modules.ebay.models.auth import  TokenResponse
from backend.modules.ebay.queries.auth import get_refresh_token_query
from backend.modules.auth.dependancies import currentActiveUser
from backend.shared.dependancies import cursorDep, currentActiveSession
from backend.modules.ebay.services import auth

ebay_auth_router = APIRouter(prefix='/auth', tags=['auth'])

@ebay_auth_router.post('/auth/exange_token')
async def do_exange_refresh_token(conn : cursorDep, user : currentActiveUser, app_id  :str):
    #check if the has a non expired token for the app
    try:
        with conn.cursor() as cursor:
            cursor.execute(get_refresh_token_query, (user.unique_id, app_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail='App not available for this user')
            return await auth.exange_refresh_token(conn, row.get('refresh_token'), user.unique_id, app_id)
    except Exception as e:
        raise
            
@ebay_auth_router.get('/refresh')
async def do_exange_token():
    pass

@ebay_auth_router.get("/token", response_model=TokenResponse)
async def exange_auth_token(conn : cursorDep,  request : Request):
    code = request.query_params.get('code')
    request_id = request.query_params.get("state")
    #next from the request_id, get the session
    try:
        session_id, app_id = auth.check_auth_request(conn, request_id)
        user = await auth.get_info_session(conn, session_id)
        user = user.get('user_id')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot confirm request info: {e}")
    #next from the session get user and app
    if code and request_id:
        return await auth.exange_auth(conn, user_id=user, code=code, app_id=app_id)
    return {'error' : 'authorization not found'}

@ebay_auth_router.post('/app/login')
async def login(conn : cursorDep, user : currentActiveUser,session_id: currentActiveSession, app_id : str):
     return auth.login_ebay(conn, user.unique_id, app_id, session_id)
   