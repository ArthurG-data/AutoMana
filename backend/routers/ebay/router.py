from fastapi import APIRouter, Query, Depends, Response
from backend.dependancies import get_settings, Settings, cursorDep
from backend.authentification import currentActiveUser
from typing import Annotated, List
from backend.routers.ebay.models import TokenInDb, InputEbaySettings
from backend.routers.ebay.auth import login_ebay, exange_auth
from backend.routers.ebay.services import register_ebay_user, register_scope, register_app
from uuid import UUID



router = APIRouter(
    tags=['ebay-routes']
)

@router.post('/register')
async def register(conn : cursorDep, user :currentActiveUser, input :InputEbaySettings ):
    try:
        register_ebay_user(input=InputEbaySettings, conn=conn, user_id=user.unique_id)
        return Response(status_code=200)
    except Exception:
        raise

@router.post('/scopes', description='add a new scope to the the available scope')
async def regist_scope(conn : cursorDep, scope: str):
    register_scope(conn, scope)
    return Response(status_code=200, content='{scope} scope added')

@router.post('/users', description='Add a ebay_user to the database that will be linked to the current user')
async def regist_user(conn: cursorDep, current_user : currentActiveUser, dev_id : UUID):
    register_ebay_user(dev_id, conn, current_user.unique_id)
    return Response(status_code=200, content='Dev added')

@router.post('/app', description='add an app to the database')
async def regist_app(conn: cursorDep, input : InputEbaySettings ):
    register_app(conn, input)
    return Response(status_code=200, content='app added')


@router.get('/login')
async def login(settings : Annotated[Settings, Depends(get_settings)]):
    return login_ebay(settings)

@router.get("/token", response_model=TokenInDb)
async def exange_auth_token(settings : Annotated[Settings, Depends(get_settings)], code : str = Query(...)):
    return exange_auth(settings, code)


@router.get('/refresh')
async def do_exange_token():
    pass