from backend.repositories.ApiRepository import ApiRepository
from backend.schemas.app_integration.ebay.auth import AuthHeader, ExangeRefreshData, AuthData, TokenResponse, TokenRequestData
from uuid import UUID, uuid4
from typing import List, Dict
import urllib
import logging

logger = logging.getLogger(__name__)

class EbayAuthAPIRepository(ApiRepository):
    URL_MAPPING = {
        "sandbox": {
            "auth_url": "https://auth.sandbox.ebay.com/oauth2/authorize",
            "token_url": "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        },
        "production": {
            "auth_url": "https://auth.ebay.com/oauth2/authorize",
            "token_url": "https://api.ebay.com/identity/v1/oauth2/token"
        }
    }
    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        super().__init__(environment=environment, timeout=timeout)

    @property
    def name(self):
        return "EbayAuthAPIRepository"
    
    def _get_base_url(self, environment: str) -> str:
        """Get the base URL for the given environment"""
        urls = self.URL_MAPPING.get(environment)
        if urls:
            return urls
        raise ValueError(f"No URL configured for environment: {environment}, url_type: {urls}")
        #if not url:
        #    raise ValueError(f"No URL configured for environment: {environment}")
        #return url

    async def request_auth_code(self, settings : Dict) -> str:
        """Request eBay OAuth authorization code"""
        params = {
            "client_id": settings["app_id"],
            "response_type": settings["response_type"],
            "redirect_uri": settings["redirect_uri"],
            "scope": " ".join(settings["scope"]),
            "state": settings["state"]
        }
        auth_url = f"{self.base_url['auth_url']}?{urllib.parse.urlencode(params)}"
        logger.info(f"Redirecting to eBay auth URL: {auth_url}")
        return auth_url

    async def  exchange_code_token(self, client_id:str, client_secret:str,code:str, redirect_uri:str)->TokenResponse :
        """Exchange authorization code for access and refresh tokens"""

        headers = AuthHeader(app_id=client_id, secret=client_secret).to_header()
        data = AuthData(code=code, redirect_uri=redirect_uri).to_data()
        response = await self._make_post_request(self._get_base_url(self.environment)['token_url'], headers=headers, data=data)
        return TokenResponse.model_validate(response)
    
    async def exchange_refresh_token(self, refresh_token: str, app_id: str, secret: str, scope: List[str]) -> dict:
        """Exchange refresh token for a new access token"""
        headers = AuthHeader(app_id=app_id, secret=secret).to_header()
        data = ExangeRefreshData(token=refresh_token, scope=scope).to_data()
        access_token = await self._make_post_request(self._get_base_url(self.environment)['token_url'], headers=headers, data=data)
        return access_token