from uuid import UUID
from backend.repositories.app_integration.ebay.ApiAuth_repository import EbayAuthAPIRepository
from backend.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from backend.repositories.app_integration.ebay.app_repository import EbayAppRepository
from backend.schemas.app_integration.ebay.auth import TokenResponse
from backend.exceptions.service_layer_exceptions.app_integration.ebay import app_exception
from backend.schemas.external_marketplace.ebay.app import NewEbayApp, AssignScope

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
    
    async def request_auth_code(self, settings: dict) -> str:
        """Request eBay OAuth authorization code"""
        return await self.http_repo.request_auth_code(settings)
    
    async def handle_callback(self, code: str, state: UUID) -> TokenResponse:
        """Handle callback from eBay with auth code"""
        # Verify this was a request we initiated
        session_id, app_id = await self.auth_repo.check_auth_request(state)
        if not session_id or not app_id:
            raise ValueError("Invalid authorization request")
        
        # Get user_id from session_id (depends on your session management)
        user_id = await self._get_user_from_session(session_id)
        
        # Get app settings
        settings = await self.app_repo.get_app_settings(user_id, app_id)
        
        # Exchange code for tokens using HTTP repository
        token_response = await self.http_repo.exchange_code_for_token(
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

    async def register_app(self, NewApp: NewEbayApp) -> bool:
        """Register an eBay app with the provided settings."""
        try:
            input = (NewApp.app_id, NewApp.redirect_uri, NewApp.response_type, NewApp.secret)
            value = await self.app_repo.add(input)
            if not value:
                raise app_exception.EbayAppRegistrationException("Failed to register eBay app")
            return True
        except app_exception.EbayAppRegistrationException as e:
            raise app_exception.EbayAppRegistrationException(f"Failed to register eBay app: {str(e)}")

    async def assign_scope(self, newScope: AssignScope) -> bool | None:
        """assign a scope to a user for an eBay app."""
        try:
            value = await self.app_repo.assign_scope(newScope.scope, newScope.app_id, newScope.user_id)
            if not value:
                raise app_exception.EbayScopeAssignmentException("Failed to assign scope to eBay app with ID: {}".format(newScope.app_id))
            return value
        except app_exception.EbayScopeAssignmentException:
            raise
        except app_exception.EbayScopeAssignmentException as e:
            raise app_exception.EbayScopeAssignmentException(f"Failed to assign scope to eBay app: {str(e)}")