from fastapi import APIRouter,Response
from backend.database.get_database import cursorDep
from backend.routers.ebay.models.auth import InputEbaySettings
from backend.routers.ebay.services.app import assign_scope, register_app, assign_app
from uuid import UUID

ebay_app_router = APIRouter(prefix='/app', tags=['app'])


@ebay_app_router.post('/app/{app_id}/scopes', description='add a scope to an app')
async def add_user_scope(conn : cursorDep, scope : str, app_id : str):
   
    try:
        assign_scope(conn,  app_id, scope)
    except Exception as e:
        return {'message' : 'Could not assign scope to app', 'error' : f'{e}'}
    return Response(status_code=200)

@ebay_app_router.post('/app', description='add an app to the database')
async def regist_app(conn: cursorDep, input : InputEbaySettings ):
    register_app(conn, input)
    return Response(status_code=200, content='app added')

@ebay_app_router.post('/app/{app_id}/{ebay_id}')
async def assign_user_app(conn: cursorDep, app_id : str, ebay_id : UUID):
    #add auhoixation later
    assign_app(conn, app_id, ebay_id)
    return Response(status_code=200, content='User assigned to app')


