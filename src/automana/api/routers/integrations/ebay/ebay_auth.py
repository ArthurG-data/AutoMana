

from fastapi import Cookie, HTTPException, APIRouter, Query, Request, Depends, Response, status
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.dependancies.auth.users import CurrentUserDep
from automana.core.models.ebay.auth import AppRegistrationRequest, CreateAppRequest
from automana.api.schemas.StandardisedQueryResponse import ApiResponse
from pydantic import BaseModel


class UpdateRedirectUriRequest(BaseModel):
    redirect_uri: str
import logging

logger = logging.getLogger(__name__)

ebay_auth_router = APIRouter(prefix='/auth', tags=['auth'])

@ebay_auth_router.post('/admin/apps'
                       , description='add an app to the database'
                       , status_code=status.HTTP_201_CREATED)
async def regist_app( 
    app_data: CreateAppRequest,
    user: CurrentUserDep,  # Only admins!
    service_manager: ServiceManagerDep
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
                 ,user: CurrentUserDep
                 ,service_manager: ServiceManagerDep
                ):
    try:

        env = await service_manager.execute_service(
            "integrations.ebay.get_environment",
            user_id=user.unique_id,
            app_code=app_code
        )
        result = await service_manager.execute_service(
            "integrations.ebay.start_oauth_flow",
            user_id=user.unique_id,
            app_code=app_code,
            environment=env
        )
        return ApiResponse(
            message="eBay OAuth flow started successfully",
            data={
                "authorization_url": result.get("authorization_url"),
            }
        )
    except Exception:
        raise

@ebay_auth_router.get("/callback")
async def handle_ebay_callback(request: Request,
                               service_manager: ServiceManagerDep,
                               code : str = Query(None),
                               state : str = Query(None),
                                error: str = Query(None),
    error_description: str = Query(None)
):
    logger.info(f"Received eBay callback: code={bool(code)}, state={state}, error={error}")
    try:
        if error:
            logger.error("ebay_callback_error", extra={"error": error, "description": error_description})
            raise HTTPException(status_code=400, detail=error_description or error)
        if not code:
            logger.error("ebay_callback_missing_params", extra={"has_code": bool(code), "has_state": bool(state)})
            raise HTTPException(status_code=400, detail="Missing authorization code in eBay callback")
        env = await service_manager.execute_service(
            "integrations.ebay.get_environment_callback",
            state=state,
            user_id=None
        )
        logger.info("ebay_callback_env", extra={"env": env})
        auth = await service_manager.execute_service(
            "integrations.ebay.process_callback",
            code=code,
            state=state,
            environment=env
        )
        logger.info("ebay_callback_success", extra={"state": state})
        return ApiResponse(
            message="eBay authorization successful",
            data={"status": "authorized", "state": state}
        )
    except HTTPException:
        raise
    except Exception:
        raise
@ebay_auth_router.patch(
    '/admin/apps/{app_code}/redirect-uri',
    description='Update the redirect URI for a registered eBay app',
    status_code=status.HTTP_200_OK,
)
async def update_redirect_uri(
    app_code: str,
    body: UpdateRedirectUriRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "integrations.ebay.update_app_redirect_uri",
            app_code=app_code,
            redirect_uri=body.redirect_uri,
        )
        return ApiResponse(
            message="Redirect URI updated successfully",
            data={
                "app_code": app_code,
                "redirect_uri": body.redirect_uri,
            },
        )
    except Exception:
        raise

from automana.api.schemas.auth.cookie import AccessTokenCookie, RefreshTokenResponse
@ebay_auth_router.post('/exange_token')
async def do_exange_refresh_token( response: Response
                                  , app_code  :str
                                  , user: CurrentUserDep
                                  , service_manager: ServiceManagerDep
                                ):
    #check if the has a non expired token for the app
    try:
        env = await service_manager.execute_service(
            "integrations.ebay.get_environment",
            user_id=user.unique_id,
            app_code=app_code
        )

        result = await service_manager.execute_service(
            "integrations.ebay.exchange_refresh_token",
            user_id=user.unique_id,
            app_code=app_code,
            environment=env
        )

        cookie_data = AccessTokenCookie(
        token=result.access_token,
        app_code=result.app_code,
        user_id=str(user.unique_id),
        expires_at=result.expires_on,
        scopes=result.scopes
        )

        # Set secure cookie
        response.set_cookie(
            key=f"ebay_access_{app_code}",
            value=cookie_data.to_cookie_value(),
            max_age=result.expires_in,
            #httponly=True,  # Prevent XSS
           # secure=True,    # HTTPS only
            samesite="strict",  # CSRF protection
            #path="/api/integrations/ebay"# Scope to eBay endpoints
        )
        logger.info(f"Access token refreshed for user {user.unique_id}, app {app_code}")

        return ApiResponse(
            message="Access token refreshed successfully",
            data={
                "expires_in": result.expires_in,
                "expires_on": result.expires_on.isoformat(),
                "scopes": result.scopes,
                "cookie_set": True,
                "cookie_name": f"ebay_access_{app_code}"
            }
        )
    except Exception as e:
        raise

