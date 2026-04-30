"""Deprecation shim — the old ``handle_selling_request`` dispatcher.

All behaviour now lives in the typed, CQS-split service modules:
- ``listings_write_service``: create / update / end
- ``listings_read_service``: get / active
- ``fulfillment_service``:   history

This module is intentionally NOT registered with ``@ServiceRegistry.register``.
It exists solely to prevent import-time breakage at call-sites that have not
yet migrated to the new typed services. It will be removed in the follow-up PR.
"""
from __future__ import annotations

import logging
import warnings
from typing import Any
from uuid import UUID

from automana.core.services.app_integration.ebay.listings_write_service import (
    create_listing,
    end_listing,
    update_listing,
)
from automana.core.services.app_integration.ebay.listings_read_service import (
    get_active_listings,
    get_listing,
)
from automana.core.services.app_integration.ebay.fulfillment_service import (
    get_order_history,
)

logger = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "handle_selling_request is deprecated and will be removed in the next PR. "
    "Call the typed services directly via ServiceManager.execute_service(path, ...)."
)


async def handle_selling_request(
    auth_repository,
    selling_repository,
    action: str,
    payload: dict[str, Any],
    **kwargs: Any,
) -> Any:
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

    app_code: str = payload.get("app_code", "")
    user_id: UUID = payload.get("user_id")
    limit: int = payload.get("limit", 10)
    offset: int = payload.get("offset", 0)

    logger.warning(
        "ebay_selling_shim_called",
        extra={
            "action": action,
            "app_code": app_code,
            "user_id": str(user_id) if user_id else None,
        },
    )

    common = dict(
        auth_repository=auth_repository,
        selling_repository=selling_repository,
        user_id=user_id,
        app_code=app_code,
    )

    if action == "create":
        return await create_listing(
            **common,
            item=payload.get("item"),
            idempotency_key=payload.get("idempotency_key", ""),
            marketplace_id=payload.get("marketplace_id", "15"),
        )
    if action == "update":
        return await update_listing(
            **common,
            item=payload.get("item"),
            marketplace_id=payload.get("marketplace_id", "15"),
        )
    if action == "delete":
        return await end_listing(
            **common,
            item_id=payload.get("item_id", ""),
            ending_reason=payload.get("ending_reason", "NotAvailable"),
            verify=payload.get("verify", False),
            marketplace_id=payload.get("marketplace_id", "15"),
        )
    if action == "get":
        return await get_listing(
            **common,
            item_id=payload.get("item_id", ""),
            marketplace_id=payload.get("marketplace_id", "15"),
        )
    if action == "get_active":
        return await get_active_listings(
            **common,
            limit=limit,
            offset=offset,
            marketplace_id=payload.get("marketplace_id", "15"),
        )
    if action == "get_history":
        return await get_order_history(
            **common,
            limit=limit,
            offset=offset,
        )

    raise ValueError(f"Unknown action: {action!r}")
