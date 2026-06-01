import asyncio
import html
import logging
import random
import re
from typing import AsyncIterator, Any, Dict, Optional, Union

import httpx

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient
from automana.core.utils.rate_limits import AsyncTokenBucket

logger = logging.getLogger(__name__)


class ShopifyAPIRepository(BaseApiClient):
    """HTTP client for the Shopify public storefront REST API.

    Rate-limits all requests via a token bucket (default: 1 req/s) and
    retries 429s with exponential backoff + jitter — same pattern as
    ApiMtgStockRepository. The service layer needs no sleep or retry logic.
    """

    def __init__(
        self,
        rate_per_sec: float = 0.8,
        burst: int = 1,
        max_attempts: int = 5,
        delay_base: float = 10.0,
        **kwargs,
    ):
        super().__init__(timeout=30)
        self.rate_limiter = AsyncTokenBucket(rate_per_sec=rate_per_sec, capacity=burst)
        self.MAX_ATTEMPTS = max_attempts
        self.DELAY_BASE = delay_base

    @property
    def name(self) -> str:
        return "ShopifyAPIRepository"

    def _get_base_url(self) -> str:
        return ""

    async def send(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data=None,
        content=None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Rate-limited send with 429 backoff — mirrors ApiMtgStockRepository.send()."""
        backoff = self.DELAY_BASE

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            await self.rate_limiter.acquire()

            resp = await super().send(
                method, endpoint,
                params=params, headers=headers, json=json,
                data=data, content=content, timeout=timeout,
            )

            if resp.status_code != 429:
                return resp

            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else backoff
            except ValueError:
                wait = backoff

            jitter = wait * (0.7 + random.random() * 0.6)
            logger.warning(
                "shopify_429_retry",
                extra={"wait_s": round(jitter, 1), "attempt": attempt, "max": self.MAX_ATTEMPTS},
            )
            await asyncio.sleep(jitter)
            backoff = min(backoff * 2, 60)

        return resp

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

        Does NOT manage the HTTP client lifecycle — caller holds it open.
        Returns empty list when there are no more products.
        """
        url = f"{api_url.rstrip('/')}/collections/{handle}/products.json"
        response = await self.send("GET", url, params={"limit": limit, "since_id": since_id})
        response.raise_for_status()
        return response.json().get("products", [])

    async def get_sitemap_collection_handles(self, api_url: str) -> list[str]:
        """Discover all collection handles from the store's Shopify sitemap."""
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
                found = re.findall(
                    r"<loc>https?://[^<]*/collections/([a-z0-9][a-z0-9\-]*[a-z0-9])</loc>",
                    resp.text,
                )
                handles.update(found)

        return list(handles)
