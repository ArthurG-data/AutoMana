"""eBay listings — read side (CQS: Queries).

Design patterns
───────────────
- **CQS (Command–Query Separation)**: this module owns reads only
  (``get_listing``, ``get_active_listings``). Writes live in
  ``listings_write_service``. Two sides, two files.
- **Guard Clause** via ``_auth_context.resolve_token`` at the top of each
  function. Fail fast before spending the API call budget.

Project rules honoured
──────────────────────
- ``logger = logging.getLogger(__name__)``.
- ``extra={}`` uses non-reserved field names only.
- Static message strings; all context in ``extra={}``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from automana.core.models.ebay import listings as listings_model
from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import (
    EbaySellingRepository,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token

logger = logging.getLogger(__name__)

DEFAULT_MARKETPLACE_ID: str = "15"


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.get",
    db_repositories=["auth"],
    api_repositories=["selling"],
)
async def get_listing(
    auth_repository: EbayAuthRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    item_id: str,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    **kwargs: Any,
) -> listings_model.ItemModel:
    """Fetch a single eBay listing by item_id and return a typed ItemModel."""
    if not item_id:
        raise ValueError("item_id is required for get_listing")

    logger.info(
        "ebay_get_listing_requested",
        extra={
            "action": "get_listing",
            "user_id": str(user_id),
            "app_code": app_code,
            "item_id": item_id,
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    payload: Dict[str, Any] = {
        "token": token,
        "item_id": item_id,
        "marketplace_id": marketplace_id,
    }
    raw = await selling_repository.get_listing(payload)

    item_data: Dict[str, Any] = (
        raw.get("GetItemResponse", {}).get("Item", {}) or {}
    )
    return listings_model.ItemModel.model_validate(item_data)


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.active",
    db_repositories=["auth"],
    api_repositories=["selling"],
)
async def get_active_listings(
    auth_repository: EbayAuthRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    limit: int = 10,
    offset: int = 0,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    **kwargs: Any,
) -> listings_model.PaginatedListings:
    """Fetch the caller's active eBay listings as a paginated result.

    eBay's GetMyeBaySelling uses 1-indexed PageNumber. We convert from the
    caller's 0-based offset so every layer of the stack speaks the same unit.
    """
    logger.info(
        "ebay_get_active_listings_requested",
        extra={
            "action": "get_active_listings",
            "user_id": str(user_id),
            "app_code": app_code,
            "limit": limit,
            "offset": offset,
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)

    # eBay's API is 1-indexed. Convert once, document why.
    page_number = (offset // limit) + 1 if limit else 1

    payload: Dict[str, Any] = {
        "token": token,
        "limit": limit,
        # The repository passes this value directly to eBay's PageNumber field.
        "offset": page_number,
        "marketplace_id": marketplace_id,
    }
    raw = await selling_repository.get_active(payload)

    active_list: Dict[str, Any] = (
        raw.get("GetMyeBaySellingResponse", {}).get("ActiveList", {}) or {}
    )

    item_array = active_list.get("ItemArray", {}) or {}
    raw_items = item_array.get("Item")

    items: List[listings_model.ItemModel] = []
    if raw_items is not None:
        # xmltodict returns a dict for a single item, a list for many.
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        for raw_item in raw_items:
            if isinstance(raw_item, dict):
                items.append(listings_model.ItemModel.model_validate(raw_item))

    raw_total: Optional[str] = (
        active_list.get("PaginationResult", {}) or {}
    ).get("TotalNumberOfEntries")

    total: Optional[int] = None
    if raw_total is not None:
        try:
            total = int(raw_total)
        except (ValueError, TypeError):
            logger.warning(
                "ebay_active_listings_total_parse_failed",
                extra={
                    "action": "get_active_listings",
                    "raw_total": str(raw_total),
                },
            )

    return listings_model.PaginatedListings.from_parts(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
