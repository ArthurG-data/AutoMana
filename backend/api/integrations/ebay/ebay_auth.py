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

from fastapi import Cookie, HTTPException, APIRouter, Query, Request, Depends, Response, status
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager, get_current_active_user
from backend.schemas.app_integration.ebay.auth import AppRegistrationRequest, CreateAppRequest
import logging

logger = logging.getLogger(__name__)

ebay_auth_router = APIRouter(prefix='/auth', tags=['auth'])


#do not add, just link
"""
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

"""    
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
                "app_code": result,
            }
        )
    except HTTPException as e:
        raise HTTPException(400, f"App registration failed: {str(e)}")
    except Exception as e:
        raise

#add an app_code later
@ebay_auth_router.post('/app/login')
async def login( 
                 app_code : str
                 ,user = Depends(get_current_active_user)
                 ,service_manager: ServiceManager = Depends(get_service_manager)
                ):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.start_oauth_flow",
            user_id=user.unique_id,
            app_code=app_code
        )
        return ApiResponse(
            message="eBay OAuth flow started successfully",
            data={
                "authorization_url": result.get("authorization_url"),
            }
        )
    except:
        pass

@ebay_auth_router.get("/callback")
async def handle_ebay_callback(request: Request,
                               code : str = Query(None),
                               state : str = Query(None),
                                error: str = Query(None),
    error_description: str = Query(None),
    service_manager: ServiceManager = Depends(get_service_manager)
):
    logger.info(f"Received eBay callback: code={bool(code)}, state={state}, error={error}")
    try:
        if error:
            logger.error(f"eBay callback error: {error}, description: {error_description}")
        #next from the request_id, get the session
        if not code or not state:
            logger.error(f"eBay callback missing parameters: code={code}, state={state}")
            raise HTTPException(status_code=400, detail="Missing code or state in eBay callback")#create exception
    ## try:
        auth = await service_manager.execute_service(
            "integrations.ebay.process_callback"
            ,code=code,
            state=state
        )
        #session_id, app_id = auth.check_auth_request(conn, request_id)
        #user = await get_info_session(conn, session_id)
        #user = user.get('user_id')
        logger.info(f"eBay callback processed successfully: {auth}")
        #except Exception as e:
        #    raise HTTPException(status_code=400, detail=f"Cannot confirm request info: {e}")
    except HTTPException:
        raise
"""
    #next from the session get user and app
    if code and request_id:
        return await auth.exange_auth(conn, user_id=user, code=code, app_id=app_id)
    return {'error' : 'authorization not found'}
"""
"""
#change to add a scope to a user
@ebay_auth_router.post('/scopes', description='add a scope to a user')
async def add_user_scope(scope : str, user_id : UUID = Path(...), queryExecutor:  QueryExecutor = Depends(get_sync_query_executor)):
    assign_scope(queryExecutor,  user_id, scope)

"""
from backend.schemas.auth.cookie import AccessTokenCookie, RefreshTokenResponse
@ebay_auth_router.post('/exange_token')
async def do_exange_refresh_token( response: Response
                                  , app_id  :str
                                  , user = Depends(get_current_active_user)
                                  , service_manager: ServiceManager = Depends(get_service_manager)
                                ):
    #check if the has a non expired token for the app
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.exchange_refresh_token",
            user_id=user.unique_id,
            app_id=app_id
        )

        cookie_data = AccessTokenCookie(
        token=result.access_token,
        app_id=result.app_id,
        user_id=str(user.unique_id),
        expires_at=result.expires_on,
        scopes=result.scopes
        )

        # Set secure cookie
        response.set_cookie(
            key=f"ebay_access_{app_id}",
            value=cookie_data.to_cookie_value(),
            max_age=result.expires_in,
            httponly=True,  # ✅ Prevent XSS
           # secure=True,    # ✅ HTTPS only
            samesite="strict",  # ✅ CSRF protection
            path="/api/integrations/ebay"  # ✅ Scope to eBay endpoints
        )
        logger.info(f"Access token refreshed for user {user.unique_id}, app {app_id}")

        return ApiResponse(
            message="Access token refreshed successfully",
            data={
                "expires_in": result.expires_in,
                "expires_on": result.expires_on.isoformat(),
                "scopes": result.scopes,
                "cookie_set": True,
                "cookie_name": f"ebay_access_{app_id}"
            }
        )


    except Exception as e:
        raise

