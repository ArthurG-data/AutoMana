from uuid import UUID
import httpx
from backend.repositories.app_integration.ebay.ApiAuth_repository import EbayAuthAPIRepository
from backend.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from backend.repositories.app_integration.ebay.app_repository import EbayAppRepository
from backend.schemas.app_integration.ebay.auth import TokenResponse
from backend.exceptions.service_layer_exceptions.app_integration.ebay import app_exception
#to removefrom backend.schemas.external_marketplace.ebay.app import NewEbayApp, AssignScope
"""
class EbayAuthService:
    def __init__(
        self, 
        auth_repo: EbayAuthRepository, 
        app_repo: EbayAppRepository,
        http_repo: EbayAuthAPIRepository
    ):
        self.auth_repo = auth_repo
        self.app_repo = app_repo
        self.http_repo = http_repo
"""
async def request_auth_code(
        auth_repository: EbayAuthRepository,
        auth_oauth_repository: EbayAuthAPIRepository,
        app_id: str,
        user_id: UUID
        ) -> str:
    """Request eBay OAuth authorization code"""
    try:
            #get app settings
        settings = await auth_repository.get_app_settings( user_id=user_id, app_id=app_id)
        if not settings:
             raise app_exception.EbayAppNotFoundException(f"eBay app with ID {app_id} not found for user {user_id}")
            #log the request
        request_id = await auth_repository.log_auth_request(user_id=user_id, app_id=app_id)
        settings["state"] = request_id
        await auth_oauth_repository.request_auth_code(settings)
    except httpx.HTTPError as e:
            raise app_exception.EbayAuthRequestException(f"Failed to request eBay auth code: {str(e)}")

async def handle_callback(auth_repository: EbayAuthRepository
                          , auth_oauth_repository: EbayAuthAPIRepository
                          , code: str
                          , state: UUID) -> TokenResponse:
    """Handle callback from eBay with auth code"""
    # Verify this was a request we initiated
    app_id, user_id = await auth_repository.check_auth_request(state)
    if not app_id or not user_id:
        raise ValueError("Invalid authorization request")
    # Get app settings
    settings = await auth_repository.get_app_settings(user_id=user_id, app_id=app_id)

    # Exchange code for tokens using HTTP repository
    token_response = await auth_oauth_repository.exchange_code_for_token(
        code=code,
        client_id=settings["app_id"],
        client_secret=settings["secret"],
        redirect_uri=settings["redirect_uri"]
    )
    
    # Save tokens using auth repository
    await self.auth_repo.save_refresh_tokens(token_response, app_id, user_id)
    await self.auth_repo.save_access_token(token_response, app_id, user_id)
    
    return token_response
    
    async def exange_refresh_token(self, app_id: str, user_id: UUID) -> str:
        """Exchange refresh token for new access token"""
        refresh_token = await self.auth_repo.get_access_from_refresh(app_id, user_id)
        if not refresh_token:
            raise ValueError("No valid refresh token found")
        
        settings = await self.app_repo.get_app_settings(user_id, app_id)
        return await self.http_repo.exchange_refresh_token(
            refresh_token=refresh_token,
            app_id=settings["app_id"],
            secret=settings["secret"],
            scope=settings["scope"]
        )

from backend.schemas.app_integration.ebay.auth import CreateAppRequest
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
                    )
            #register the app
            app_id = await app_repository.add(input)
            if not app_id:
                raise app_exception.EbayAppRegistrationException("Failed to register eBay app")
            #register the app scopes
            await app_repository.register_app_scopes(app_id, app_data.allowed_scopes)
            return app_id
        except app_exception.EbayAppRegistrationException as e:
            raise app_exception.EbayAppRegistrationException(f"Failed to register eBay app: {str(e)}")
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