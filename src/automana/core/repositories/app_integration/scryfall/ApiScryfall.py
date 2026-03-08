from datetime import datetime
import pathlib

import io

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient
import aiohttp
from typing import AsyncGenerator, Dict, Any
import httpx
import logging
logger = logging.getLogger(__name__)

class ScryfallAPIRepository(BaseApiClient):
    BASE_URL = "https://api.scryfall.com"

    def __init__(self, timeout: int = 30, **kwargs):
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

    def _get_base_url(self) -> str:
        """Return the base URL for the given environment"""
        return self.BASE_URL
    
    async def migrations_to_bytes_buffer(self) -> io.BytesIO:
        buffer = io.BytesIO()
        
        async for m in self._fetch_migrations():
            line = "\t".join([
                m.get("id", ""),
                m.get("uri", ""),
                m.get("performed_at", ""),
                m.get("migration_strategy", ""),
                m.get("old_scryfall_id", ""),
                m.get("new_scryfall_id", ""),
                (m.get("note") or "").replace("\t", " ").replace("\n", " "),
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
            ]) + "\n"

            buffer.write(line.encode("utf-8"))  # âœ… bytes

        buffer.seek(0)
        return buffer

    
    async def _fetch_migrations(self) -> AsyncGenerator[Dict[str, Any], None]:
        endpoint = "/migrations?page=1"
        full_url = self.get_full_url(endpoint) 
        async with self._get_client() as client:
            while full_url:
                response = await self._get(full_url)
                data = response.json()
                for m in data.get("data", []):
                    yield m

                full_url = data.get("next_page")

    
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
    
    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        result = await self.send(method="GET", endpoint=endpoint)
        return result
    
    async def add():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
    async def update():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
    async def delete():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
    async def list():
        raise NotImplementedError("Use specific methods for Scryfall API interactions")
