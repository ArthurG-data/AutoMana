"""eBay fulfillment — order history query and local status transitions.

Design patterns
───────────────
- CQS: reads and simple local writes share this module; heavyweight writes
  (eBay API calls) live in ``fulfillment_write_service``.
- Guard Clause via ``_auth_context.resolve_token``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from automana.core.models.ebay import listings as listings_model
from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.selling.fulfillment.history",
    db_repositories=["auth", "app"],
    api_repositories=["selling"],
)
async def get_order_history(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    limit: int = 10,
    offset: int = 0,
    **kwargs: Any,
) -> listings_model.PaginatedOrders:
    """Fetch order history from the eBay Fulfillment API, merged with local status."""
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
    env = await auth_repository.get_environment(app_code=app_code)
    if env:
        selling_repository.environment = env.lower()
    payload: Dict[str, Any] = {"token": token, "limit": limit, "offset": offset}
    raw = await selling_repository.get_history(payload)

    raw_orders = raw.get("orders") or []
    items: List[listings_model.FulfillmentResponse] = []
    for order in raw_orders:
        if isinstance(order, dict):
            items.append(listings_model.FulfillmentResponse.model_validate(order))

    # Merge local status overrides.
    if items:
        order_ids = [o.orderId for o in items if o.orderId]
        local_map = await app_repository.get_order_statuses(
            app_code=app_code, order_ids=order_ids
        )
        for item in items:
            if item.orderId and item.orderId in local_map:
                item.local_status = local_map[item.orderId].get("local_status")

    raw_total: Optional[Any] = raw.get("total")
    total: Optional[int] = None
    if raw_total is not None:
        try:
            total = int(raw_total)
        except (ValueError, TypeError):
            logger.warning(
                "ebay_order_history_total_parse_failed",
                extra={"action": "get_order_history", "raw_total": str(raw_total)},
            )

    return listings_model.PaginatedOrders.from_parts(
        items=items, total=total, offset=offset, limit=limit,
    )


@ServiceRegistry.register(
    path="integrations.ebay.selling.fulfillment.local_status",
    db_repositories=["auth", "app"],
    api_repositories=[],
)
async def update_order_local_status(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    user_id: UUID,
    order_id: str,
    app_code: str,
    local_status: str,
    **kwargs: Any,
) -> Dict[str, str]:
    """Update the AutoMana-local lifecycle status for an order (no eBay call)."""
    await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    logger.info(
        "ebay_update_order_local_status",
        extra={"action": "update_order_local_status", "order_id": order_id, "local_status": local_status},
    )
    await app_repository.upsert_order_status(
        order_id=order_id,
        app_code=app_code,
        local_status=local_status,
    )
    return {"order_id": order_id, "local_status": local_status}
