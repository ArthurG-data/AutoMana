from automana.core.repositories.app_integration.ebay.EbayApiRepository import EbayApiClient
from automana.core.models.ebay.auth import AuthHeader, ExangeRefreshData, AuthData, TokenResponse, TokenRequestData
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
        self.environment = environment.lower()
        super().__init__(timeout=timeout)

    @property
    def name(self):
        return "EbayBrowseAPIRepository"

    def _get_base_url(self) -> str:
        url = self.URL_MAPPING.get(self.environment)
        if not url:
            raise ValueError(f"No URL configured for environment: {self.environment}")
        return url
    
    async def search_items(
        self,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        try:
            logger.info(f"Searching items in {self.environment} with params: {data}")
            response = await self.send(
                "GET", "/item_summary/search", params=data, headers=headers or None
            )
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Error searching items: {str(e)}")
            raise
