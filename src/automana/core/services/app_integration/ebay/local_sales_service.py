"""Read-only service for locally-persisted eBay sold orders."""
from __future__ import annotations

import logging
from typing import Any

from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.selling.local_sales.list",
    db_repositories=["ebay_sales"],
    runs_in_transaction=False,
)
async def list_local_sales(
    ebay_sales_repository: EbaySalesRepository,
    user_id: str,
    app_code: str,
    limit: int = 25,
    offset: int = 0,
    **kwargs: Any,
) -> dict:
    rows, total = await ebay_sales_repository.list_local_sales(
        user_id=user_id,
        app_code=app_code,
        limit=limit,
        offset=offset,
    )
    has_more = (offset + len(rows)) < total
    logger.info(
        "ebay_local_sales_listed",
        extra={"app_code": app_code, "total": total, "returned": len(rows)},
    )
    return {"items": rows, "total": total, "has_more": has_more}
