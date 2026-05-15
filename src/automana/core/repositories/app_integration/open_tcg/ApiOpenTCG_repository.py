import asyncio
import logging
from typing import Any

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient

logger = logging.getLogger(__name__)

_MTG_CATEGORY = 1
_MAX_CONCURRENT_SETS = 20


class OpenTCGAPIRepository(BaseApiClient):
    """HTTP client for the Open TCG API (tcgtracking.com).

    Free, no auth, CDN-cached. Updated daily at 08:00 EST.
    All endpoints are scoped to Magic: The Gathering (category 1).
    """

    BASE_URL = "https://tcgtracking.com/tcgapi/v1"

    def __init__(self, timeout: int = 30, **kwargs):
        super().__init__(timeout=timeout)

    @property
    def name(self) -> str:
        return "OpenTCGAPIRepository"

    def _get_base_url(self) -> str:
        return self.BASE_URL

    def default_headers(self) -> dict:
        return {"Accept": "application/json", "User-Agent": "AutoMana/1.0"}

    async def get_sets(self) -> list[dict]:
        """GET /1/sets — returns all MTG sets."""
        response = await self.send("GET", f"/{_MTG_CATEGORY}/sets")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else data.get("sets", [])

    async def get_set_skus(self, set_id: int) -> list[dict]:
        """GET /1/sets/{set_id}/skus — SKU-level condition/finish/language prices.

        Response shape: {"products": {"<product_id>": {"<sku_id>": {cnd, var, lng, mkt, low, hi}}}}
        Flattened to: [{"product_id": str, "cnd": ..., "var": ..., ...}, ...]
        """
        response = await self.send("GET", f"/{_MTG_CATEGORY}/sets/{set_id}/skus")
        response.raise_for_status()
        data = response.json()
        products = data.get("products", {}) if isinstance(data, dict) else {}
        rows: list[dict] = []
        for product_id, skus in products.items():
            if not isinstance(skus, dict):
                continue
            for sku in skus.values():
                if isinstance(sku, dict):
                    rows.append({"product_id": product_id, **sku})
        return rows

    async def get_set_pricing(self, set_id: int) -> dict[str, Any]:
        """GET /1/sets/{set_id}/pricing — Manapool pricing for the set."""
        response = await self.send("GET", f"/{_MTG_CATEGORY}/sets/{set_id}/pricing")
        response.raise_for_status()
        return response.json()

    async def get_all_set_skus(self, set_ids: list[int]) -> dict[int, list[dict]]:
        """Fetch SKUs for all sets concurrently in batches of MAX_CONCURRENT_SETS.

        Returns a mapping of set_id → list of SKU dicts.
        """
        results: dict[int, list[dict]] = {}
        sem = asyncio.Semaphore(_MAX_CONCURRENT_SETS)

        async def _fetch(sid: int) -> tuple[int, list[dict]]:
            async with sem:
                try:
                    skus = await self.get_set_skus(sid)
                    return sid, skus
                except Exception:
                    logger.warning(
                        "opentcg_skus_fetch_failed",
                        extra={"set_id": sid},
                    )
                    return sid, []

        tasks = [asyncio.create_task(_fetch(sid)) for sid in set_ids]
        for coro in asyncio.as_completed(tasks):
            sid, skus = await coro
            results[sid] = skus
            logger.debug(
                "opentcg_skus_fetched",
                extra={"set_id": sid, "sku_count": len(skus)},
            )

        return results
