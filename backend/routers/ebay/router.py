from fastapi import APIRouter, Query, Depends, Response
from backend.dependancies import get_settings, Settings, cursorDep
from backend.authentification import currentActiveUser
from typing import Annotated, List
from backend.routers.ebay.models import TokenInDb, InputEbaySettings
from backend.routers.ebay.auth import login_ebay, exange_auth
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




@router.get("/token", response_model=TokenInDb)
async def exange_auth_token(settings : Annotated[Settings, Depends(get_settings)], code : str = Query(...)):
    return exange_auth(settings, code)


@router.get('/refresh')
async def do_exange_token():
    pass