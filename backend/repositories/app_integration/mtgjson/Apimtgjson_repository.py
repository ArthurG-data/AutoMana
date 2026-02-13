from backend.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient
from backend.core.settings import Settings
import logging

class ApimtgjsonRepository(BaseApiClient):
    def __init__(self
                   , environment: str 
                 ,  timeout: int = 30
                 ,settings: Settings = None):
        super().__init__(timeout=timeout)

    def name(self) -> str:
        return "ApimtgjsonRepository"
    
    def _get_base_url(self) -> str:
        return "https://mtgjson.com/api/v5"
    
    def default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": "AutoMana/1.0"
        }
    

    async def fetch_all_prices_data(self) -> dict:
        """Fetch the data from the previous 90 days"""
        return await self._get("AllPrices.json.xz")
    
    async def fetch_price_today(self) -> dict:
        return await self._get("AllPricesToday.json.xz")
    

    async def fetch_card_data(self, extension) -> dict:
        return await self._get(extension)
    
    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        headers = self.default_headers()
        result = await self.request(method="GET", endpoint=endpoint, headers=headers)
        return result
    
