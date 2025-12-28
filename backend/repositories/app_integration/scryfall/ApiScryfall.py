import pathlib
from backend.repositories.ApiRepository import ApiRepository
import aiohttp

class ScryfallAPIRepository(ApiRepository):
    BASE_URL = "https://api.scryfall.com"

    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        super().__init__(environment=environment, timeout=timeout)
        self.environment = environment
        self.timeout = timeout

    @property
    def name(self):
        return "ScryfallAPIRepository"
    
    def _get_base_url(self, environment: str) -> str:
        """Return the base URL for the given environment"""
        return self.BASE_URL

    async def download_data_from_url(self, url) -> dict:
        """Fetch the Scryfall bulk data manifest"""
        #url = f"{self._get_base_url(self.environment)}/{url.lstrip('/')}" not needed because db stores full url
        response = await self._make_get_request(url)
        data = response.json() if hasattr(response, 'json') else response
        if callable(data):
            data = await response.json()
        file_size = len(str(data).encode('utf-8'))
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