"""
from backend.modules.ebay.models.auth import  TokenResponse
from backend.repositories.app_integration.ebay.auth_queries import get_refresh_token_query
from backend.modules.auth.dependancies import currentActiveUser
from backend.shared.dependancies import cursorDep, currentActiveSession
from backend.modules.ebay.services import auth
from backend.modules.auth.services import get_info_session
from fastapi import APIRouter,Response, Depends, Path
from backend.database.get_database import cursorDep
from backend.modules.ebay.models.auth import InputEbaySettings
from backend.modules.ebay.services.app import assign_scope, register_app, assign_app
from uuid import UUID
from backend.services_old.shop_data_ingestion.db.dependencies import get_sync_query_executor
from backend.services_old.shop_data_ingestion.db import QueryExecutor
from fastapi import APIRouter,Response, Depends
from backend.database.get_database import cursorDep
from backend.modules.auth.dependancies import currentActiveUser
from backend.modules.ebay.services.dev import register_ebay_user
from uuid import UUID
from backend.services_old.shop_data_ingestion.db import QueryExecutor
from backend.services_old.shop_data_ingestion.db.dependencies import get_sync_query_executor
"""
from typing import List
from fastapi import HTTPException, APIRouter, Request, Depends, status
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager, get_current_active_user
from backend.schemas.app_integration.ebay.auth import AppRegistrationRequest, CreateAppRequest

ebay_auth_router = APIRouter(prefix='/auth', tags=['auth'])


#do not add, just link
@ebay_auth_router.post('/app/register'
                       , description='Add a ebay_user to the database that will be linked to the current user'
                       , status_code=status.HTTP_201_CREATED)
async def regist_user(app_registration : AppRegistrationRequest
                      , current_user = Depends(get_current_active_user)
                      ,service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        dev_id = await service_manager.execute_service(
            "integrations.ebay.register_dev",
            app_code=app_registration.app_code,
            scopes=app_registration.scopes,
            agreement=app_registration.agreement,
            user_id=current_user.unique_id
        )
    except HTTPException as e:
        raise HTTPException(status_code=400, detail=f"App registration failed: {str(e)}")
    except Exception:
        raise
    #register_ebay_user(dev_id, current_user.unique_id, service_manager)

    
from backend.request_handling.StandardisedQueryResponse import ApiResponse
@ebay_auth_router.post('/admin/apps'
                       , description='add an app to the database'
                       , status_code=status.HTTP_201_CREATED)
async def regist_app( 
    app_data: CreateAppRequest,
    user = Depends(get_current_active_user),  # Only admins!
    service_manager: ServiceManager = Depends(get_service_manager)
):
    try:
        result =await service_manager.execute_service(
            "integrations.ebay.register_app",
            app_data=app_data,
            created_by=user
        )
        return ApiResponse(
            message="App registered successfully",
            data={
                "message": "eBay app registered successfully",
                "app_code": result["app_code"],
                "app_id": result["app_id"],
                "validation_results": result["validation_results"],
                "available_to": result["available_to"]
            }
        )
    except HTTPException as e:
        raise HTTPException(400, f"App registration failed: {str(e)}")
    except Exception as e:
        raise

"""
#change to add a scope to a user
@ebay_auth_router.post('/scopes', description='add a scope to a user')
async def add_user_scope(scope : str, user_id : UUID = Path(...), queryExecutor:  QueryExecutor = Depends(get_sync_query_executor)):
    assign_scope(queryExecutor,  user_id, scope)


@ebay_auth_router.post('/exange_token')
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
async def do_exange_token(conn: cursorDep, app_id, user : currentActiveUser):
    try:
        return await auth.get_access_from_refresh(user.unique_id,app_id, conn)
    except Exception as e:
        return {"Errro refreshing" : str(e)}

@ebay_auth_router.get("/token", response_model=TokenResponse)
async def exange_auth_token(conn : cursorDep,  request : Request):
    code = request.query_params.get('code')
    request_id = request.query_params.get("state")
    #next from the request_id, get the session
    try:
        session_id, app_id = auth.check_auth_request(conn, request_id)
        user = await get_info_session(conn, session_id)
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
"""