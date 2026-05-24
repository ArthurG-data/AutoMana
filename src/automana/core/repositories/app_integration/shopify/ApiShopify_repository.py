import logging
from typing import AsyncIterator

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient

logger = logging.getLogger(__name__)


class ShopifyAPIRepository(BaseApiClient):

    def __init__(self, **kwargs):
        super().__init__(timeout=30)

    @property
    def name(self) -> str:
        return "ShopifyAPIRepository"

    def _get_base_url(self) -> str:
        return ""

    async def iter_products_pages(self, api_url: str, source_id: int) -> AsyncIterator[tuple[int, list[dict]]]:
        """Paginate /products.json, yielding (page_index, products_list) per page."""
        page = 0
        next_url = f"{api_url.rstrip('/')}/products.json?limit=250"

        async with self:
            while next_url:
                response = await self.send("GET", next_url)
                response.raise_for_status()
                data = response.json()
                products = data.get("products") or data.get("items") or []
                if not products:
                    break
                yield page, products
                page += 1
                link_header = response.headers.get("link", "")
                next_url = None
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split(";")[0].strip().strip("<>")
                        break
