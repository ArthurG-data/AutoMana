from backend.repositories.ApiRepository import ApiRepository
from backend.schemas.app_integration.ebay.auth import AuthHeader, ExangeRefreshData, AuthData, TokenResponse, TokenRequestData
from uuid import UUID, uuid4
from typing import List, Dict
import urllib
import logging

logger = logging.getLogger(__name__)

class EbayAuthAPIRepository(ApiRepository):
    AUTH_URL = "https://auth.ebay.com/oauth2/authorize"
    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"  # Base URL for eBay Buy API, use a factory later to create the repos, and have the url in a db
    def __init__(self, base_url: str = None, timeout: int = 30):
        self.API_URL = base_url or self.AUTH_URL
        self.TOKEN_URL = self.TOKEN_URL
        super().__init__(self.API_URL, timeout)

    @property
    def name(self):
        return "EbayAuthAPIRepository"

    async def request_auth_code(self, settings : Dict) -> str:
        """Request eBay OAuth authorization code"""
        params = {
            "client_id": settings["app_id"],
            "response_type": settings["response_type"],
            "redirect_uri": settings["redirect_uri"],
            "scope": " ".join(settings["scope"]),
            "secret": settings["secret"],
            "state": settings["state"]
        }
        auth_url = f"https://auth.ebay.com/oauth2/authorize?{urllib.parse.urlencode(params)}"
        logger.info(f"Redirecting to eBay auth URL: {auth_url}")
        await self._make_post_request(auth_url)
    
    async def  exchange_code_token(self, app_id:str, secret:str,code:str, redirect_uri:str)->TokenResponse :
        """Exchange authorization code for access and refresh tokens"""
        headers = AuthHeader(app_id=app_id,secret=secret ).to_header()
        data = AuthData(code = code, redirect_uri = redirect_uri).to_data()
        response = await self._make_post_request(self.API_URL, headers=headers, xml=data)
        return TokenResponse.model_validate(response)
    
    async def exchange_refresh_token(self, refresh_token: str, app_id: str, secret: str, scope: List[str]) -> str:
        """Exchange refresh token for a new access token"""
        headers = AuthHeader(app_id=app_id, secret=secret).to_header()
        data = ExangeRefreshData(token=refresh_token, scope=scope).to_data()
        access_token = await self._make_post_request(self.TOKEN_URL, headers=headers, xml=data)
        return access_token