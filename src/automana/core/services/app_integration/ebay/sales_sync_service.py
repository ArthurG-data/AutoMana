"""eBay sold-price persistence — own-sales channel.

Two registered services:
- track_active_listing: called from router after listing creation (best-effort)
- sync_own_sales: nightly service iterating all active sellers
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)
from automana.core.repositories.app_integration.ebay.app_repository import (
    EbayAppRepository,
)
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import (
    EbaySellingRepository,
)
from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.repositories.card_catalog.card_repository import (
    CardReferenceRepository,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token
from automana.core.services.app_integration.ebay.market_price_scorer import score_title
from automana.core.models.ebay.listings import FulfillmentResponse, LineItemType

logger = logging.getLogger(__name__)

_EBAY_SOURCE_ID = 5
_SCORE_THRESHOLD = 0.7


def _price_to_cents(value: Any) -> Optional[int]:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _parse_sold_at(date_str: Optional[str]) -> datetime:
    if date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def _resolve_card_version(
    item_id: Optional[str],
    title: str,
    ebay_sales_repository: EbaySalesRepository,
    card_repository: CardReferenceRepository,
) -> Optional[UUID]:
    if item_id:
        cv = await ebay_sales_repository.get_card_version_by_item(item_id)
        if cv:
            return cv

    candidates = await card_repository.suggest(query=title, limit=10)
    best_cv: Optional[UUID] = None
    best_score = _SCORE_THRESHOLD
    for c in candidates:
        sc = score_title(
            title,
            card_name=c.get("card_name", ""),
            set_code=c.get("set_code"),
            is_foil=None,
            frame=None,
        )
        if sc >= best_score:
            best_score = sc
            best_cv = UUID(str(c["card_version_id"]))
    return best_cv


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.track_active_listing",
    db_repositories=["ebay_sales"],
    runs_in_transaction=False,
)
async def track_active_listing(
    ebay_sales_repository: EbaySalesRepository,
    item_id: str,
    app_code: str,
    card_version_id: UUID,
    **kwargs: Any,
) -> None:
    """Persist item_id → card_version_id after a listing is created."""
    await ebay_sales_repository.upsert_active_listing(
        item_id=item_id,
        app_code=app_code,
        card_version_id=card_version_id,
        listed_at=datetime.now(timezone.utc),
    )
    logger.info(
        "ebay_active_listing_tracked",
        extra={"item_id": item_id, "app_code": app_code},
    )


@ServiceRegistry.register(
    path="integrations.ebay.sync_own_sales",
    db_repositories=["auth", "app", "ebay_sales", "card"],
    api_repositories=["selling"],
    runs_in_transaction=False,
)
async def sync_own_sales(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    ebay_sales_repository: EbaySalesRepository,
    card_repository: CardReferenceRepository,
    selling_repository: EbaySellingRepository,
    days_back: int = 90,
    **kwargs: Any,
) -> dict:
    """Fetch all sellers' eBay order history and upsert into staging tables."""
    active_users = await auth_repository.get_active_app_code_users()
    if not active_users:
        logger.info("ebay_sync_own_sales_no_active_users")
        return {"synced_orders": 0}

    total_orders = 0
    for row in active_users:
        user_id: UUID = UUID(str(row["user_id"]))
        app_code: str = row["app_code"]
        try:
            await _sync_for_user(
                user_id=user_id,
                app_code=app_code,
                auth_repository=auth_repository,
                app_repository=app_repository,
                ebay_sales_repository=ebay_sales_repository,
                card_repository=card_repository,
                selling_repository=selling_repository,
            )
            total_orders += 1
        except Exception:
            logger.exception(
                "ebay_sync_own_sales_user_failed",
                extra={"user_id": str(user_id), "app_code": app_code},
            )
    return {"synced_orders": total_orders}


async def _sync_for_user(
    user_id: UUID,
    app_code: str,
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    ebay_sales_repository: EbaySalesRepository,
    card_repository: CardReferenceRepository,
    selling_repository: EbaySellingRepository,
) -> None:
    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    env = await auth_repository.get_environment(app_code=app_code)
    if env:
        selling_repository.environment = env.lower()

    payload = {"token": token, "limit": 50, "offset": 0}
    raw = await selling_repository.get_history(payload)
    raw_orders = raw.get("orders") or []

    for order_data in raw_orders:
        if not isinstance(order_data, dict):
            continue
        order = FulfillmentResponse.model_validate(order_data)
        if not order.orderId:
            continue

        try:
            await app_repository.upsert_order_status(
                order_id=order.orderId,
                app_code=app_code,
                local_status="sold",
            )
        except Exception:
            logger.warning(
                "ebay_sync_upsert_status_failed",
                extra={"order_id": order.orderId, "app_code": app_code},
            )

        for line in (order.lineItems or []):
            await _process_line_item(
                order=order,
                line=line,
                app_code=app_code,
                ebay_sales_repository=ebay_sales_repository,
                card_repository=card_repository,
            )


async def _process_line_item(
    order: FulfillmentResponse,
    line: LineItemType,
    app_code: str,
    ebay_sales_repository: EbaySalesRepository,
    card_repository: CardReferenceRepository,
) -> None:
    item_id = line.legacyItemId
    title = line.title or ""
    sold_at = _parse_sold_at(order.creationDate)
    buyer = order.buyer.username if order.buyer else None

    price_val = line.lineItemCost.text if line.lineItemCost else None
    price_cents = _price_to_cents(price_val)
    if price_cents is None:
        logger.warning(
            "ebay_sync_line_item_no_price",
            extra={"order_id": order.orderId, "item_id": item_id},
        )
        return

    currency = (
        line.lineItemCost.currencyID if line.lineItemCost else "USD"
    ) or "USD"

    card_version_id = await _resolve_card_version(
        item_id=item_id,
        title=title,
        ebay_sales_repository=ebay_sales_repository,
        card_repository=card_repository,
    )

    source_product_id: Optional[int] = None
    if card_version_id:
        try:
            source_product_id = await ebay_sales_repository.ensure_source_product(
                card_version_id, _EBAY_SOURCE_ID
            )
        except Exception:
            logger.exception(
                "ebay_sync_ensure_source_product_failed",
                extra={"card_version_id": str(card_version_id)},
            )
            return

    try:
        await ebay_sales_repository.upsert_order_source_product(
            order_id=order.orderId,
            app_code=app_code,
            item_id=item_id or "",
            title=title,
            source_product_id=source_product_id,
            quantity=line.quantity or 1,
            sold_price_cents=price_cents,
            currency=currency,
            finish_id=1,
            condition_id=None,
            language_id=1,
            sold_at=sold_at,
            buyer_username=buyer,
        )
    except Exception:
        logger.exception(
            "ebay_sync_upsert_order_source_product_failed",
            extra={"order_id": order.orderId, "item_id": item_id},
        )
