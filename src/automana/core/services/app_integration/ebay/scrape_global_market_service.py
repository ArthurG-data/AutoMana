"""eBay global market scraper — nightly sold-price collection across US, AU, CA markets."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
)
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.repositories.card_catalog.card_repository import (
    CardReferenceRepository,
)
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)
from automana.core.services.app_integration.ebay.title_parser import (
    CONDITION_ID_MAP,
    FINISH_ID_MAP,
    conflicts_with_expected,
    parse_condition_code,
    parse_finish_code,
    parse_frame_variant,
)
from automana.core.config.settings import get_settings
import redis.asyncio as aioredis
from automana.core.services.app_integration.ebay.ebay_raw_io import (
    load_items_from_json,
    watchlist_path,
    write_items_to_json,
)
from automana.core.services.app_integration.ebay.ebay_api_quota import (
    quota_increment,
    quota_remaining,
)

logger = logging.getLogger(__name__)

_EBAY_SOURCE_ID = 5
_DEFAULT_LANGUAGE_ID = 1
_MARKETPLACES = ("EBAY-US", "EBAY-AU", "EBAY-ENCA")
_INTER_MARKETPLACE_DELAY = 1.0   # 1 req/s per marketplace — stays well below burst throttle
_INTER_CARD_DELAY = 0.5          # breathing room between cards
_API_DAILY_BUDGET = 5_000


@ServiceRegistry.register(
    path="integrations.ebay.scrape_global_market",
    db_repositories=["ebay_sales", "ebay_scrape", "card"],
    api_repositories=["ebay_finding"],
    runs_in_transaction=False,
)
async def scrape_global_market(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    card_repository: CardReferenceRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    days_back: int = 30,
    score_threshold: float = 0.7,
    limit_per_card: int = 100,
    **kwargs: Any,
) -> dict:
    """Scrape sold prices for watchlist cards across EBAY-US, EBAY-AU, EBAY-ENCA."""
    settings = get_settings()
    app_id = getattr(settings, "ebay_app_id", None)
    if not app_id:
        logger.warning("scrape_global_market_no_app_id")
        return {"scraped_items": 0, "cards_processed": 0}

    targets = await ebay_scrape_repository.get_scrape_targets()
    if not targets:
        logger.info("scrape_global_market_no_targets")
        return {"scraped_items": 0, "cards_processed": 0}

    min_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    redis_host = getattr(settings, "redis_host", "localhost")
    redis_port = getattr(settings, "redis_port", 6379)
    redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}/0")

    total_items = 0

    try:
        for card_version_id in targets:
            card = await card_repository.get_scrape_metadata(card_version_id)
            if not card:
                logger.warning(
                    "scrape_global_market_card_not_found",
                    extra={"card_version_id": str(card_version_id)},
                )
                continue

            product_id = await ebay_sales_repository.ensure_product(card_version_id)
            if not product_id:
                logger.warning(
                    "scrape_global_market_ensure_product_failed",
                    extra={"card_version_id": str(card_version_id)},
                )
                continue

            source_product_id = await ebay_sales_repository.ensure_source_product(
                card_version_id, _EBAY_SOURCE_ID
            )
            if not source_product_id:
                logger.warning(
                    "scrape_global_market_ensure_source_product_failed",
                    extra={"card_version_id": str(card_version_id)},
                )
                continue

            for marketplace in _MARKETPLACES:
                try:
                    count = await _scrape_one_card(
                        card_version_id=card_version_id,
                        card=card,
                        app_id=app_id,
                        marketplace=marketplace,
                        min_date=min_date,
                        limit_per_card=limit_per_card,
                        score_threshold=score_threshold,
                        ebay_sales_repository=ebay_sales_repository,
                        ebay_scrape_repository=ebay_scrape_repository,
                        ebay_finding_repository=ebay_finding_repository,
                        source_product_id=source_product_id,
                        today=today,
                        redis_client=redis_client,
                    )
                    total_items += count
                except Exception:
                    logger.exception(
                        "scrape_global_market_card_marketplace_failed",
                        extra={
                            "card_version_id": str(card_version_id),
                            "marketplace": marketplace,
                        },
                    )
                await asyncio.sleep(_INTER_MARKETPLACE_DELAY)
            else:
                try:
                    await ebay_scrape_repository.update_target_last_scraped(card_version_id)
                except Exception:
                    logger.warning(
                        "scrape_global_market_update_last_scraped_failed",
                        extra={"card_version_id": str(card_version_id)},
                    )
                await asyncio.sleep(_INTER_CARD_DELAY)
    finally:
        await redis_client.aclose()

    logger.info(
        "scrape_global_market_complete",
        extra={"scraped_items": total_items, "cards_processed": len(targets)},
    )
    return {"scraped_items": total_items, "cards_processed": len(targets)}


async def _scrape_one_card(
    card_version_id: UUID,
    card: dict,
    app_id: str,
    marketplace: str,
    min_date: datetime,
    limit_per_card: int,
    score_threshold: float,
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    source_product_id: int,
    today: str,
    redis_client,
) -> int:
    card_name: str = card.get("card_name", "")
    set_code: Optional[str] = card.get("set_code")
    frame_effects: list[str] = card.get("frame_effects") or []
    is_borderless: bool = (card.get("border_color_name") or "").lower() == "borderless"

    primary_frame = frame_effects[0] if frame_effects else (
        "borderless" if is_borderless else None
    )
    keywords = build_query_string(
        card_name=card_name,
        set_code=set_code,
        is_foil=None,
        frame=primary_frame,
    )

    json_path = watchlist_path(today, source_product_id, marketplace)

    if json_path.exists():
        try:
            items = load_items_from_json(json_path)
            logger.info(
                "scrape_global_market_replay",
                extra={"source_product_id": source_product_id, "marketplace": marketplace},
            )
        except ValueError:
            logger.warning(
                "scrape_global_market_corrupt_watchlist_file",
                extra={"path": str(json_path)},
            )
            json_path.unlink(missing_ok=True)
            items = await _fetch_watchlist_items(
                keywords, app_id, marketplace, min_date, limit_per_card,
                ebay_finding_repository, json_path, source_product_id, redis_client, today,
            )
    else:
        items = await _fetch_watchlist_items(
            keywords, app_id, marketplace, min_date, limit_per_card,
            ebay_finding_repository, json_path, source_product_id, redis_client, today,
        )

    count = 0
    for item in items:
        title: str = item.get("title", "")

        sc = score_title(
            title,
            card_name=card_name,
            set_code=set_code,
            is_foil=None,
            frame=primary_frame,
        )
        if sc < score_threshold:
            continue

        parsed_frame = parse_frame_variant(title)
        if conflicts_with_expected(parsed_frame, card):
            continue

        price_cents = _to_cents(item.get("price"))
        if price_cents is None:
            continue

        finish_code = parse_finish_code(title)
        finish_id = FINISH_ID_MAP.get(finish_code, 1)

        condition_code = parse_condition_code(item.get("condition"), title)
        condition_id = CONDITION_ID_MAP.get(condition_code, 1)

        currency: str = item.get("currency") or "USD"
        item_id: str = item.get("item_id") or ""
        sold_at = _parse_sold_date(item.get("sold_date"))

        await ebay_scrape_repository.insert_scraped_sold(
            item_id=item_id,
            title=title,
            source_product_id=source_product_id,
            price_cents=price_cents,
            currency=currency,
            marketplace_id=marketplace,
            condition_id=condition_id,
            finish_id=finish_id,
            language_id=_DEFAULT_LANGUAGE_ID,
            sold_at=sold_at,
        )
        count += 1

    return count


async def _fetch_watchlist_items(
    keywords: str,
    app_id: str,
    marketplace: str,
    min_date: datetime,
    limit_per_card: int,
    ebay_finding_repository: EbayFindingAPIRepository,
    json_path,
    source_product_id: int,
    redis_client,
    today: str,
) -> list[dict]:
    if await quota_remaining(redis_client, today, _API_DAILY_BUDGET) == 0:
        logger.warning(
            "scrape_global_market_quota_exhausted",
            extra={"source_product_id": source_product_id, "marketplace": marketplace},
        )
        return []

    async def _on_page():
        await quota_increment(redis_client, today)

    items = await ebay_finding_repository.find_completed_items(
        keywords=keywords,
        app_id=app_id,
        global_id=marketplace,
        min_date=min_date,
        limit=limit_per_card,
        max_pages=3,
        on_page_fetched=_on_page,
    )

    try:
        write_items_to_json(json_path, items, marketplace, source_product_id=source_product_id)
    except OSError:
        logger.error(
            "scrape_global_market_watchlist_write_failed", extra={"path": str(json_path)}
        )
    return items


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
