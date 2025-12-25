from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
import httpx
from backend.repositories.app_integration.ebay.ApiAuth_repository import EbayAuthAPIRepository
from backend.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from backend.repositories.app_integration.ebay.app_repository import EbayAppRepository
from backend.schemas.app_integration.ebay.auth import TokenResponse
from backend.exceptions.service_layer_exceptions.app_integration.ebay import app_exception
from backend.schemas.auth.cookie import RefreshTokenResponse
import logging

logger = logging.getLogger(__name__)
#to removefrom backend.schemas.external_marketplace.ebay.app import NewEbayApp, AssignScope
from backend.core.service_registry import ServiceRegistry

@ServiceRegistry.register(
        'integrations.ebay.start_oauth_flow',
        api_repositories=['auth_oauth']
)
async def request_auth_code(
        auth_repository: EbayAuthRepository,
        auth_oauth_repository: EbayAuthAPIRepository,
        app_code: str,
        user_id: UUID
        ) -> str:
    """Request eBay OAuth authorization code"""  
    try:
            #get app settings
        settings = await auth_repository.get_app_settings( user_id=user_id, app_code=app_code)
        if not settings:
             raise app_exception.EbayAppNotFoundException(f"eBay app with code {app_code} not found for user {user_id}")
        #get the scopes
        scopes = await auth_repository.get_app_scopes(app_id=settings["app_id"])
        if not scopes:
            raise app_exception.EbayAppScopeNotFoundException(f"No scopes found for eBay app with code {app_code}")
        #log the request
        settings["scope"] = scopes
        request_id = await auth_repository.log_auth_request(user_id=user_id, app_id=settings["app_id"])
        if not request_id:
            raise app_exception.EbayAuthRequestException("Failed to log eBay OAuth request")
        settings["state"] = request_id
        url = await auth_oauth_repository.request_auth_code(settings)
        return {"authorization_url": url}
    except httpx.HTTPError as e:
            raise app_exception.EbayAuthRequestException(f"Failed to request eBay auth code: {str(e)}")


@ServiceRegistry.register(
        'integrations.ebay.get_environment_callback',
        db_repositories=['auth'],
        api_repositories=['auth_oauth']
)
async def get_environment_callback(auth_repository: EbayAuthRepository
                          , state: str
                          , user_id: Optional[UUID]=None) -> str:
    
    """Get eBay environment callback"""
    try:
        env = await auth_repository.get_env_from_callback(user_id=user_id, state=state)
        if not env:
            raise app_exception.EbayAppNotFoundException(f"eBay app with state {state} not found for user {user_id}")
        return env
    except httpx.HTTPError as e:
        raise app_exception.EbayAuthRequestException(f"Failed to get eBay environment: {str(e)}")

@ServiceRegistry.register(
        'integrations.ebay.Pprocess_callback',
        db_repositories=['auth'],
        api_repositories=['auth_oauth']
)
async def handle_callback(auth_repository: EbayAuthRepository
                          , auth_oauth_repository: EbayAuthAPIRepository
                          , code: str
                          , state: UUID
                          ) -> TokenResponse:
    """Handle callback from eBay with auth code"""
    # Verify this was a request we initiated
    app_id, user_id, app_code = await auth_repository.check_auth_request(state)
    if not app_code or not user_id:
        raise ValueError("Invalid authorization request")
    # Get app settings
    settings = await auth_repository.get_app_settings(user_id=user_id, app_code=app_code)

    # Exchange code for tokens using HTTP repository
    token_response = await auth_oauth_repository.exchange_code_token(
        code=code,
        client_id=settings["app_id"],
        client_secret=settings["decrypted_secret"],
        redirect_uri=settings["redirect_uri"]
    )
    
    # Save tokens using auth repository
    await auth_repository.save_refresh_tokens(token_response, app_id, user_id)
    await auth_repository.save_access_token(token_response, app_id, user_id)
    logger.info(f"Tokens saved for app {app_id} and user {user_id}")

@ServiceRegistry.register(
        'integrations.ebay.exchange_refresh_token',
        db_repositories=['auth'],
        api_repositories=['auth_oauth']
)
async def exchange_refresh_token(auth_repository: EbayAuthRepository
                          , auth_oauth_repository: EbayAuthAPIRepository
                          , app_code: str
                          , user_id: UUID) -> RefreshTokenResponse:
    """Exchange refresh token for new access token"""
    refresh_token = await auth_repository.get_access_from_refresh(app_code, user_id)
    if not refresh_token:
        raise ValueError("No valid refresh token found")

    settings = await auth_repository.get_app_settings(user_id=user_id, app_code=app_code)
    scopes = await auth_repository.get_app_scopes(app_id=settings["app_id"])
    
    result = await auth_oauth_repository.exchange_refresh_token(
        refresh_token=refresh_token,
        app_id=settings["app_id"],
        secret=settings["decrypted_secret"],
        scope=scopes if scopes else []
    )
    if not result.get("access_token"):
        raise ValueError("No valid access token found")
    #store the new access token
    token = TokenResponse(
        access_token=result.get("access_token"),
        expires_in=result.get("expires_in"),
        expires_on=datetime.now() + timedelta(seconds=result.get("expires_in")),
        token_type=result.get("token_type")
    )

    await auth_repository.save_access_token(token, app_id=settings["app_id"], user_id=user_id)
    return RefreshTokenResponse(
        success=True,
        message="Refresh token exchanged successfully",
        access_token=result.get("access_token"),
        expires_in=result.get("expires_in"),
        expires_on=datetime.now() + timedelta(seconds=result.get("expires_in")),
        token_type=result.get("token_type"),
        scopes=scopes,
        cookie_set=True,
        app_code=app_code
    )

from backend.schemas.app_integration.ebay.auth import CreateAppRequest

@ServiceRegistry.register(
        'integrations.ebay.register_app',
        db_repositories=['app']
)
async def register_app(app_repository: EbayAppRepository
                       , app_data : CreateAppRequest
                       , created_by:UUID) -> bool:
        """Register an eBay app with the provided settings."""
        try:
            input = ( app_data.ebay_app_id
                    ,app_data.app_name
                     , app_data.redirect_uri
                     , app_data.response_type
                     , app_data.client_secret
                     , app_data.environment.value
                     , app_data.description
                     , app_data.app_code
                    )
            #register the app
            app_code = await app_repository.add(input)
            if not app_code:
                raise app_exception.EbayAppRegistrationException("Failed to register eBay app")
            #register the app scopes
            await app_repository.register_app_scopes(app_data.ebay_app_id, app_data.allowed_scopes)
            return app_code
        except app_exception.EbayAppRegistrationException as e:
            raise app_exception.EbayAppRegistrationException(f"Failed to register eBay app: {str(e)}")

async def get_access_token(auth_repository: EbayAuthRepository
                           , app_code: str
                           , user_id: Optional[UUID]=None) -> str | None:
    """Get the access token for a user and app code."""
    try:
        token = await auth_repository.get_valid_access_token(user_id=user_id, app_code=app_code)
        if not token:
            raise app_exception.EbayAccessTokenException("No valid access token found")
        return token
    except app_exception.EbayAccessTokenException as e:
        raise app_exception.EbayAccessTokenException(f"Failed to get access token: {str(e)}")

@ServiceRegistry.register(
        'integrations.ebay.get_environment',
        db_repositories=['auth']
)
async def get_environment(auth_repository: EbayAuthRepository
                          , app_code: str
                          , user_id: Optional[UUID]=None) -> str | None:
    """Get the environment for a user and app code."""
    try:
        env = await auth_repository.get_environment(user_id=user_id, app_code=app_code)
        if not env:
            raise app_exception.EbayEnvironmentException("No valid environment found")
        return env
    except app_exception.EbayEnvironmentException as e:
        raise app_exception.EbayEnvironmentException(f"Failed to get environment: {str(e)}")

"""
    async def assign_scope(self, newScope: AssignScope) -> bool | None:
     
        try:
            value = await self.app_repo.assign_scope(newScope.scope, newScope.app_id, newScope.user_id)
            if not value:
                raise app_exception.EbayScopeAssignmentException("Failed to assign scope to eBay app with ID: {}".format(newScope.app_id))
            return value
        except app_exception.EbayScopeAssignmentException:
            raise
        except app_exception.EbayScopeAssignmentException as e:
            raise app_exception.EbayScopeAssignmentException(f"Failed to assign scope to eBay app: {str(e)}")
"""