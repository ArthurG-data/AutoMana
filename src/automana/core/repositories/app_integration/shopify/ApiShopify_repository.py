import html
import logging
import re
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

    async def get_collection_products_page(
        self,
        api_url: str,
        handle: str,
        since_id: int = 0,
        limit: int = 250,
    ) -> list[dict]:
        """Fetch one page of products from a collection via since_id pagination.

        Does NOT manage the HTTP client lifecycle — the caller must hold
        the client open (via ``async with repo:``) across concurrent calls.
        Returns empty list when there are no more products.
        """
        url = f"{api_url.rstrip('/')}/collections/{handle}/products.json"
        response = await self.send("GET", url, params={"limit": limit, "since_id": since_id})
        response.raise_for_status()
        return response.json().get("products", [])

    async def get_sitemap_collection_handles(self, api_url: str) -> list[str]:
        """Discover all collection handles from the store's Shopify sitemap.

        Fetches /sitemap.xml, finds sitemap_collections_*.xml links, then
        extracts collection handles from each collections sitemap.
        Returns a deduplicated list of handles.
        """
        async with self:
            sitemap_resp = await self.send("GET", f"{api_url.rstrip('/')}/sitemap.xml")
            sitemap_resp.raise_for_status()

            collection_sitemap_links = re.findall(
                r"<loc>(https?://[^<]+sitemap_collections_[^<]+)</loc>",
                sitemap_resp.text,
            )

            handles: set[str] = set()
            for link in collection_sitemap_links:
                resp = await self.send("GET", html.unescape(link))
                resp.raise_for_status()
                found = re.findall(r"/collections/([^<\s?#/]+)", resp.text)
                handles.update(found)

        return list(handles)
