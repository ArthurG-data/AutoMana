from backend.repositories.abstract_repositories.AbstractAPIRepository import AbstractAPIRepository
from backend.core.settings import Settings
import logging

class ApimtgjsonRepository(AbstractAPIRepository):
    def __init__(self, settings: Settings)  :
        super().__init__( settings)

        

    def name(self) -> str:
        return "ApimtgjsonRepository"
    
    def _get_base_url(self) -> str:
        return "https://mtgjson.com/api/v5"
    
    def default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": "AutoMana/1.0"
        }
    
    async def fetch_card_data(self, extension) -> dict:
        return await self._get(extension)
    
    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{self._get_base_url()}/{endpoint}"
        headers = self.default_headers()
        async with self._session.get(url, headers=headers) as response:
            response.raise_for_status()
            return await response.json()
    
