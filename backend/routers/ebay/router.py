
from fastapi import APIRouter,Response, Request, HTTPException
from backend.routers.ebay import queries
from backend.database.get_database import cursorDep
from backend.routers.auth.depndancies import currentActiveUser
from backend.routers.ebay.models import TokenResponse, InputEbaySettings
from backend.routers.ebay.auth import login_ebay, exange_auth, exange_refresh_token
from backend.routers.ebay.services import register_ebay_user,assign_scope, register_scope, register_app, assign_app
from uuid import UUID

router = APIRouter(
    tags=['ebay-routes']
)

@router.post('/scopes/', description='add a new scope to the the available scope', tags=['scopes'])
async def regist_scope(conn : cursorDep, scope: str):
    register_scope(conn, scope)
    return Response(status_code=200, content='{scope} scope added')

@router.post('/dev/register', description='Add a ebay_user to the database that will be linked to the current user', tags=['dev'])
async def regist_user(conn: cursorDep, current_user : currentActiveUser, dev_id : UUID):
    register_ebay_user(dev_id, conn, current_user.unique_id)
    return Response(status_code=200, content='Dev added')

@router.post('/app/login')
async def login(conn : cursorDep, user : currentActiveUser, app_id : str):
     return login_ebay(conn, user.unique_id, app_id)
   

@router.post('/app/{app_id}/scopes', description='add a scope to an app', tags=['app'])
async def add_user_scope(conn : cursorDep, scope : str, app_id : str):
    assign_scope(conn,  app_id, '{scope}')
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


@router.get('/callback')
async def check_token(request : Request):
    code = request.query_params.get('code')
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    user_agent = request.headers.get("user-agent")
    state = request.headers.get("state")
    if code:
        return {'code' : code,
                 'origin': origin,
                 'referer' : referer,
                 'user_agent': user_agent, 
                 'state' : state}
    return {'error' : 'authorization not found'}

@router.get("/token", response_model=TokenResponse)
async def exange_auth_token(conn : cursorDep,  request : Request, user : UUID = 'to add'):
    code = request.query_params.get('code')
    if code:
        return await exange_auth(conn, user_id=user, code=code)
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