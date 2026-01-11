from backend.repositories.app_integration.ebay.EbayApiRepository import EbayApiClient
from backend.schemas.app_integration.ebay.auth import AuthHeader, ExangeRefreshData, AuthData, TokenResponse, TokenRequestData
from uuid import UUID, uuid4
from typing import List, Dict, Any, Optional
import urllib
import logging

logger = logging.getLogger(__name__)

class EbayBrowseAPIRepository(EbayApiClient):
    URL_MAPPING = {
        "sandbox": "https://api.sandbox.ebay.com/buy/browse/v1",
        "production": "https://api.ebay.com/buy/browse/v1"
    }
    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        super().__init__(environment=environment, timeout=timeout)

    @property
    def name(self):
        return "EbayBrowseAPIRepository"
    
    def _get_base_url(self, environment: str) -> str:
        """Get the base URL for the given environment"""
        url = self.URL_MAPPING.get(environment)
        if not url:
            raise ValueError(f"No URL configured for environment: {environment}")
        return url
    
    async def search_items(
        self,
        data : Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        xml: Optional[str] = None
    ) -> str:
        try:

            logger.info(f"Searching items in {self.environment} with params: {data}")
            response = await self._make_get_request(
                "/item_summary/search"
                ,params=data, headers=headers if headers else None
                , xml=xml)
            return response
        except Exception as e:
            logger.error(f"Error searching items: {str(e)}")
            raise