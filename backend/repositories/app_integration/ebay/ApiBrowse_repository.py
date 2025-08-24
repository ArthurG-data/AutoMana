from backend.repositories.ApiRepository import ApiRepository
from backend.schemas.app_integration.ebay.auth import AuthHeader, ExangeRefreshData, AuthData, TokenResponse, TokenRequestData
from uuid import UUID, uuid4
from typing import List, Dict, Any, Optional
import urllib
import logging

logger = logging.getLogger(__name__)

class EbayBrowseAPIRepository(ApiRepository):
    PRODUCTION_URL = "https://api.ebay.com/buy/browse/v1/item_summary"  # Base URL for eBay Buy API, use a factory later to create the repos, and have the url in a db
    SANDBOX_URL = "https://api.sandbox.ebay.com/buy/browse/v1/item_summary"
    def __init__(self, base_url: str = None, timeout: int = 30):
        self.API_URL = base_url or self.PRODUCTION_URL

        super().__init__(self.API_URL, timeout)

    @property
    def name(self):
        return "EbayBrowseAPIRepository"
    
    async def search_items(
        self,
        data : Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        xml: Optional[str] = None
    ) -> str:
        try:
            response = await self._make_get_request(f"{self.SANDBOX_URL}/search",params=data, headers=headers if headers else None, xml=xml)
            return response
        except Exception as e:
            logger.error(f"Error searching items: {str(e)}")
            raise