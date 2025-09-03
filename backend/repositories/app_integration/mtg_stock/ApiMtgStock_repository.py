import asyncio, httpx, hashlib, json
from asyncio.log import logger
from typing import Dict, List, Optional

class ApiMtgStockRepository:
    def __init__(self, environment: str):
        self.base_url = "https://api.mtgstocks.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        self.DELAY_BASE = 180
        self.SEM = asyncio.Semaphore(8)
        self.environment = environment

        self.client = None

    def name(self) -> str:
        """Return the name of the repository"""
        return "API_Repository"

    async def __aenter__(self):
        """Initialize the persistent HTTP client when entering the context."""
        self.client = httpx.AsyncClient(http2=True)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Close the persistent HTTP client when exiting the context."""
        await self.client.aclose()

    async def _make_get_request(self, endpoint: str):
        backoff = self.DELAY_BASE
        url = f"{self.base_url}{endpoint}"
        logger.info(f"Fetching JSON from {url}")
        for attempt in range(6):
            try:
                r = await self.client.get(url, headers=self.headers, timeout=30)
                if r.status_code == 429:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                elif r.status_code == 404:
                    logger.warning(f"Resource not found: {url}")
                    return None
                r.raise_for_status()
                return r.content
            except httpx.HTTPError:
                if attempt == 5:
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def fetch_card_prices(self, card_id: int):
        endpoint = f"/prints/{card_id}/prices"
        return await self._make_get_request(endpoint)
    
    async def fetch_card_details(self, card_id: int):
        endpoint = f"/prints/{card_id}"
        return await self._make_get_request(endpoint)

    async def fetch_card_data_batches(self, card_ids: List[int]) -> List[Dict]:
        
        async def fetch_data(card_id: int):
            async with self.SEM:
                try:
                    details_task = self.fetch_card_details(card_id)
                    prices_task = self.fetch_card_prices(card_id)
                    details, prices = await asyncio.gather(details_task, prices_task)
                    if details is None or prices is None:
                        return {"card_id": card_id, "error": "Data not found"}
                    return {"card_id": card_id, "details": details, "prices": prices}
                except httpx.HTTPStatusError as e:
                    return {"card_id": card_id, "error": str(e)}
            
        tasks = [fetch_data(card_id) for card_id in card_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append({"error": str(result)})
            else:
                processed_results.append(result)
        return processed_results

