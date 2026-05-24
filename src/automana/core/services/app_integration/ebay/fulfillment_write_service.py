# src/automana/core/services/app_integration/ebay/fulfillment_write_service.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.selling.fulfillment.ship",
    db_repositories=["auth", "app"],
    api_repositories=["selling"],
)
async def mark_order_shipped(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    order_id: str,
    line_item_ids: List[str],
    tracking_number: Optional[str] = None,
    carrier_code: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Call eBay's Fulfillment API to mark an order shipped, then persist locally."""
    logger.info(
        "ebay_mark_order_shipped_requested",
        extra={
            "action": "mark_order_shipped",
            "user_id": str(user_id),
            "app_code": app_code,
            "order_id": order_id,
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    env = await auth_repository.get_environment(app_code=app_code)
    if env:
        selling_repository.environment = env.lower()

    result = await selling_repository.create_shipping_fulfillment({
        "token": token,
        "order_id": order_id,
        "line_item_ids": line_item_ids,
        "tracking_number": tracking_number,
        "carrier_code": carrier_code,
    })

    await app_repository.upsert_order_status(
        order_id=order_id,
        app_code=app_code,
        local_status="sent",
        tracking_number=tracking_number,
        carrier_code=carrier_code,
        shipped_at=datetime.now(timezone.utc),
    )

    logger.info(
        "ebay_mark_order_shipped_success",
        extra={"action": "mark_order_shipped", "order_id": order_id},
    )
    return result
