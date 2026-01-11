import pathlib
from backend.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient
import aiohttp
from typing import Optional
import httpx
import logging
logger = logging.getLogger(__name__)

class ScryfallAPIRepository(BaseApiClient):
    BASE_URL = "https://api.scryfall.com"

    def __init__(self, timeout: int = 30, **kwargs):
        self.client: Optional[httpx.AsyncClient] = None
        super().__init__(timeout=timeout)
        self.timeout = timeout
        # persistent client used when entering context
       

    @property
    def name(self):
        return "ScryfallAPIRepository"
    
    
    def default_headers(self):
        return {
            "Accept": "application/json",
            "User-Agent": "AutoMana/1.0"
        }
         
    async def __aenter__(self):
        """Initialize the persistent HTTP client when entering the context."""
        self.client = httpx.AsyncClient(http2=True, timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Close the persistent HTTP client when exiting the context."""
        if self.client:
            await self.client.aclose()
            self.client = None

    def _get_base_url(self) -> str:
        """Return the base URL for the given environment"""
        return self.BASE_URL

    async def download_data_from_url(self, url) -> dict:
        """Fetch the Scryfall bulk data manifest"""
        #url = f"{self._get_base_url(self.environment)}/{url.lstrip('/')}" not needed because db stores full url
        data = await self.request("GET", url, headers=self.default_headers())
        file_size = len(str(data).encode("utf-8"))
        return {"data": data, "file_size": file_size}
    
    async def stream_download(self, url: str, out_path: pathlib.Path, chunk_size: int = 1024 * 1024):
        """
        Stream download a file from the given URL to out_path.
        """
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        f.write(chunk)

        tmp.replace(out_path)
    
    async def get():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
    async def add():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
    async def update():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
    async def delete():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
    async def list():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")