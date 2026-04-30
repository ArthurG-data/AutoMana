"""eBay fulfillment — order history query.

Design patterns
───────────────
- **CQS (Command–Query Separation)**: this module owns the fulfillment
  bounded context (order history). Listings live in ``listings_read_service``
  and ``listings_write_service``.
- **Guard Clause** via ``_auth_context.resolve_token``.

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


@ServiceRegistry.register(
    path="integrations.ebay.selling.fulfillment.history",
    db_repositories=["auth"],
    api_repositories=["selling"],
)
async def get_order_history(
    auth_repository: EbayAuthRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    limit: int = 10,
    offset: int = 0,
    **kwargs: Any,
) -> listings_model.PaginatedOrders:
    """Fetch order history from the eBay Fulfillment API."""
    logger.info(
        "ebay_get_order_history_requested",
        extra={
            "action": "get_order_history",
            "user_id": str(user_id),
            "app_code": app_code,
            "limit": limit,
            "offset": offset,
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    payload: Dict[str, Any] = {
        "token": token,
        "limit": limit,
        "offset": offset,
    }
    raw = await selling_repository.get_history(payload)

    raw_orders = raw.get("orders") or []
    items: List[listings_model.FulfillmentResponse] = []
    for order in raw_orders:
        if isinstance(order, dict):
            items.append(listings_model.FulfillmentResponse.model_validate(order))

    raw_total: Optional[Any] = raw.get("total")
    total: Optional[int] = None
    if raw_total is not None:
        try:
            total = int(raw_total)
        except (ValueError, TypeError):
            logger.warning(
                "ebay_order_history_total_parse_failed",
                extra={
                    "action": "get_order_history",
                    "raw_total": str(raw_total),
                },
            )

    return listings_model.PaginatedOrders.from_parts(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
