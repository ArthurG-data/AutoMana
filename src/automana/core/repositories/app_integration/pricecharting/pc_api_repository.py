"""HTTP client for PriceCharting public endpoints (httpx-based, no JS required)."""
from __future__ import annotations

import logging

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class PricechartingApiRepository(BaseApiClient):
    BASE_URL = "https://www.pricecharting.com"

    def __init__(self, timeout: float = 30.0, **kwargs):
        super().__init__(timeout=timeout, http2=False)

    @property
    def name(self) -> str:
        return "PricechartingApiRepository"

    def default_headers(self) -> dict[str, str]:
        return {"User-Agent": _USER_AGENT}

    def _get_base_url(self) -> str:
        return self.BASE_URL

    async def fetch_sets(self) -> list[dict]:
        """GET /consoles-autocomplete/magic-cards → [{label, value}, ...]."""
        response = await self.send("GET", "/consoles-autocomplete/magic-cards")
        data = self._parse_response(response)
        if isinstance(data, list):
            return data
        return data.get("results", data.get("items", []))

    async def fetch_sales_html(self, url: str) -> str:
        """GET an individual card page and return raw HTML (server-rendered, no JS needed)."""
        response = await self.send("GET", url)
        return response.text
