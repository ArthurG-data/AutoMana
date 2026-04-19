"""HTTP client for the MTGJson public API.

Thin Adapter over `BaseApiClient` — the generic streaming and error-mapping
lives in the parent; this class only declares the endpoints that matter.
"""
import logging
from pathlib import Path

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient
from automana.core.settings import Settings

logger = logging.getLogger(__name__)


class ApimtgjsonRepository(BaseApiClient):
    """MTGJson v5 API client.

    Base URL: https://mtgjson.com/api/v5
    All endpoints are public and unauthenticated, so `default_headers` is
    limited to `Accept` and a courteous `User-Agent`.
    """

    # The `environment` and `settings` params are accepted but unused today
    # because the factory that constructs this class passes them uniformly
    # across API repositories. Keeping the signature aligned with the factory
    # contract is cheaper than bespoke plumbing per integration.
    def __init__(
        self,
        environment: str,
        timeout: int = 30,
        settings: Settings = None,
    ):
        super().__init__(timeout=timeout)

    def name(self) -> str:
        return "ApimtgjsonRepository"

    def _get_base_url(self) -> str:
        return "https://mtgjson.com/api/v5"

    def default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": "AutoMana/1.0",
        }

    # --- Eager (in-memory) fetches -------------------------------------------------
    # These return the full response into memory. For the `.xz` archives —
    # which run to hundreds of MB — prefer the `_stream` variants below.

    async def fetch_all_prices_data(self) -> bytes:
        """Fetch the 90-day `AllPrices.json.xz` archive as bytes (memory-heavy)."""
        response = await self.send(method="GET", endpoint="AllPrices.json.xz")
        return self._parse_response(response)

    async def fetch_price_today(self) -> bytes:
        """Fetch today's `AllPricesToday.json.xz` archive as bytes (memory-heavy)."""
        response = await self.send(method="GET", endpoint="AllPricesToday.json.xz")
        return self._parse_response(response)

    # --- Streaming fetches (preferred for the `.xz` archives) ----------------------

    async def fetch_price_today_stream(self, dest_path: Path) -> Path:
        """Stream `AllPricesToday.json.xz` directly to `dest_path`."""
        return await self.stream_download("AllPricesToday.json.xz", dest_path)

    async def fetch_all_prices_stream(self, dest_path: Path) -> Path:
        """Stream the 90-day `AllPrices.json.xz` directly to `dest_path`."""
        return await self.stream_download("AllPrices.json.xz", dest_path)

    # --- Metadata ------------------------------------------------------------------

    async def fetch_meta(self) -> dict:
        """Fetch `Meta.json` — catalog version/date used by idempotency gates."""
        response = await self.send(method="GET", endpoint="Meta.json")
        return self._parse_response(response)

    async def fetch_card_data(self, extension: str) -> dict:
        """Fetch an arbitrary JSON endpoint under the v5 base URL."""
        response = await self.send(method="GET", endpoint=extension)
        return self._parse_response(response)
