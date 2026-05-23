"""eBay sold-price persistence — external-scrape channel.

Scrapes completed listings from the Finding API for each card the seller
has listed, inserts results into pricing.ebay_scraped_sold (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)
from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
)
from automana.core.repositories.card_catalog.card_repository import (
    CardReferenceRepository,
)
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_EBAY_SOURCE_ID = 5
_RATE_LIMIT_DELAY = 1.0  # seconds between cards — stays below Finding API burst throttle


@ServiceRegistry.register(
    path="integrations.ebay.scrape_external_sold",
    db_repositories=["auth", "ebay_sales", "ebay_scrape", "card"],
    api_repositories=["ebay_finding"],
    runs_in_transaction=False,
)
async def scrape_external_sold(
    auth_repository: EbayAuthRepository,
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    card_repository: CardReferenceRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    days_back: int = 30,
    score_threshold: float = 0.7,
    limit_per_card: int = 100,
    **kwargs: Any,
) -> dict:
    """Scrape external sold listings for every card the seller has listed."""
    settings = get_settings()
    app_id = settings.ebay_app_id
    if not app_id:
        logger.warning("ebay_scrape_external_sold_no_app_id")
        return {"scraped_items": 0}

    active_users = await auth_repository.get_active_app_code_users()
    if not active_users:
        logger.info("ebay_scrape_external_sold_no_active_users")
        return {"scraped_items": 0}

    total = 0
    seen_app_codes: set[str] = set()

    for row in active_users:
        app_code: str = row["app_code"]
        if app_code in seen_app_codes:
            continue
        seen_app_codes.add(app_code)

        try:
            card_version_ids = await ebay_sales_repository.get_listed_card_versions(app_code)
        except Exception:
            logger.exception(
                "ebay_scrape_get_listed_versions_failed",
                extra={"app_code": app_code},
            )
            continue

        min_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        for card_version_id in card_version_ids:
            try:
                count = await _scrape_one_card(
                    card_version_id=card_version_id,
                    app_id=app_id,
                    min_date=min_date,
                    limit_per_card=limit_per_card,
                    score_threshold=score_threshold,
                    card_repository=card_repository,
                    ebay_finding_repository=ebay_finding_repository,
                    ebay_sales_repository=ebay_sales_repository,
                    ebay_scrape_repository=ebay_scrape_repository,
                )
                total += count
            except Exception:
                logger.exception(
                    "ebay_scrape_card_failed",
                    extra={"card_version_id": str(card_version_id)},
                )
            await asyncio.sleep(_RATE_LIMIT_DELAY)

    return {"scraped_items": total}


async def _scrape_one_card(
    card_version_id: UUID,
    app_id: str,
    min_date: datetime,
    limit_per_card: int,
    score_threshold: float,
    card_repository: CardReferenceRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
) -> int:
    card = await card_repository.get(card_version_id)
    if not card:
        return 0

    card_name = card.get("card_name", "")
    set_code = card.get("set_code")
    keywords = build_query_string(
        card_name=card_name,
        set_code=set_code,
        is_foil=None,
        frame=None,
    )

    items = await ebay_finding_repository.find_completed_items(
        keywords=keywords,
        app_id=app_id,
        min_date=min_date,
        limit=limit_per_card,
    )

    count = 0
    for item in items:
        title = item.get("title", "")
        sc = score_title(
            title,
            card_name=card_name,
            set_code=set_code,
            is_foil=None,
            frame=None,
        )
        if sc < score_threshold:
            continue

        price_cents = _to_cents(item.get("price"))
        if price_cents is None:
            continue

        sold_at = _parse_sold_date(item.get("sold_date"))
        currency = item.get("currency") or "USD"
        item_id = item.get("item_id") or ""

        try:
            source_product_id = await ebay_sales_repository.ensure_source_product(
                card_version_id, _EBAY_SOURCE_ID
            )
        except Exception:
            logger.exception(
                "ebay_scrape_ensure_source_product_failed",
                extra={"card_version_id": str(card_version_id)},
            )
            continue

        await ebay_scrape_repository.insert_scraped_sold(
            item_id=item_id,
            title=title,
            source_product_id=source_product_id,
            price_cents=price_cents,
            currency=currency,
            marketplace_id="EBAY-US",
            condition_id=None,
            finish_id=1,
            language_id=1,
            sold_at=sold_at,
        )
        count += 1

    return count


def _to_cents(value: Any) -> Optional[int]:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _parse_sold_date(date_str: Optional[str]) -> datetime:
    if date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
