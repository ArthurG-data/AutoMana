from datetime import datetime, timezone
from typing import Any, Optional
import asyncio
import logging

from automana.core.repositories.app_integration.ebay.EbayApiRepository import EbayApiClient

logger = logging.getLogger(__name__)

_FINDING_ENDPOINT = "/services/search/FindingService/v1"
_SERVICE_VERSION = "1.13.0"
_MAX_RATE_LIMIT_RETRIES = 3


def _is_rate_limited(data: Any) -> bool:
    """Return True if the response contains errorId 10001 (Finding API burst throttle)."""
    try:
        errors = data.get("errorMessage", [{}])[0].get("error", [])
        return any(e.get("errorId", [""])[0] == "10001" for e in errors)
    except (IndexError, KeyError, TypeError, AttributeError):
        return False


def _parse_finding_items(response: dict) -> list[dict]:
    """Extract a flat list of raw item dicts from the Finding API JSON response."""
    try:
        result_block = response["findCompletedItemsResponse"][0]
        ack = result_block.get("ack", [None])[0]
        if ack not in ("Success", "SuccessWithError", None):
            error_msg = result_block.get("errorMessage", [{}])[0]
            logger.warning(
                "Finding API returned non-success ack",
                extra={"ack": ack, "error": str(error_msg)[:300]},
            )
            return []
        search_result = result_block.get("searchResult", [{}])[0]
        raw_items = search_result.get("item", [])
    except (KeyError, IndexError):
        logger.warning("Finding API response missing expected envelope", extra={"keys": list(response.keys())})
        return []

    out = []
    for item in raw_items:
        try:
            selling = item.get("sellingStatus", [{}])[0]
            price_block = selling.get("currentPrice", [{}])[0]
            listing_info = item.get("listingInfo", [{}])[0]
            condition_block = item.get("condition", [{}])[0]

            out.append({
                "item_id": item.get("itemId", [""])[0],
                "title": item.get("title", [""])[0],
                "price": float(price_block.get("__value__", 0)),
                "currency": price_block.get("currencyId", ""),
                "condition": condition_block.get("conditionDisplayName", [None])[0],
                "url": item.get("viewItemURL", [None])[0],
                "sold_date": listing_info.get("endTime", [None])[0],
            })
        except Exception:
            logger.warning("Skipping unparseable Finding API item", extra={"raw": str(item)[:200]})
            continue

    return out


class EbayFindingAPIRepository(EbayApiClient):
    URL_MAPPING = {
        "sandbox": "https://svcs.sandbox.ebay.com",
        "production": "https://svcs.ebay.com",
    }

    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        self.environment = environment.lower()
        super().__init__(timeout=timeout)

    @property
    def name(self) -> str:
        return "EbayFindingAPIRepository"

    def _get_base_url(self) -> str:
        url = self.URL_MAPPING.get(self.environment)
        if not url:
            raise ValueError(f"No Finding API URL for environment: {self.environment}")
        return url

    async def find_completed_items(
        self,
        keywords: str,
        app_id: str,
        *,
        global_id: str = "EBAY-US",
        category_id: int = 2536,
        condition_id: Optional[int] = None,
        min_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "OPERATION-NAME": "findCompletedItems",
            "SERVICE-VERSION": _SERVICE_VERSION,
            "SECURITY-APPNAME": app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "GLOBAL-ID": global_id,
            "keywords": keywords,
            "categoryId": str(category_id),
            "itemFilter(0).name": "SoldItemsOnly",
            "itemFilter(0).value": "true",
            "paginationInput.entriesPerPage": str(min(limit, 100)),
            "paginationInput.pageNumber": "1",
        }

        filter_idx = 1
        if condition_id is not None:
            params[f"itemFilter({filter_idx}).name"] = "Condition"
            params[f"itemFilter({filter_idx}).value"] = str(condition_id)
            filter_idx += 1

        if min_date is not None:
            if min_date.tzinfo is None:
                raise ValueError("min_date must be timezone-aware (UTC)")
            utc_date = min_date.astimezone(timezone.utc)
            params[f"itemFilter({filter_idx}).name"] = "EndTimeFrom"
            params[f"itemFilter({filter_idx}).value"] = utc_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        logger.info(
            "Finding API request",
            extra={"keywords": keywords, "category_id": category_id, "limit": limit},
        )
        for attempt in range(_MAX_RATE_LIMIT_RETRIES):
            async with self:
                response = await self.send("GET", _FINDING_ENDPOINT, params=params)
                data = self._parse_response(response)

            if _is_rate_limited(data):
                wait = (2 ** attempt) + 5
                logger.warning(
                    "finding_api_rate_limited",
                    extra={"attempt": attempt + 1, "wait_seconds": wait, "keywords": keywords},
                )
                if attempt < _MAX_RATE_LIMIT_RETRIES - 1:
                    await asyncio.sleep(wait)
                    continue
                return []

            return _parse_finding_items(data)

        return []
