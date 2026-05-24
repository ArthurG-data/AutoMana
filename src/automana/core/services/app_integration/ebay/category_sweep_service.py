"""eBay daily category-wide sweep — fetch all MTG sold listings, match to known cards."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis

from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
)
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay.market_price_scorer import score_title
from automana.core.services.app_integration.ebay.title_parser import (
    CONDITION_ID_MAP,
    FINISH_ID_MAP,
    parse_condition_code,
    parse_finish_code,
)
from automana.core.services.app_integration.ebay.ebay_raw_io import (
    load_or_fetch_items,
    parse_sold_date,
    sweep_path,
    to_cents,
    write_items_to_json,
)
from automana.core.services.app_integration.ebay.ebay_api_quota import (
    quota_increment,
    quota_remaining,
)
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_MARKETPLACES = ("EBAY-US", "EBAY-AU", "EBAY-ENCA")
_DEFAULT_LANGUAGE_ID = 1
_SCORE_THRESHOLD = 0.5
_SWEEP_MAX_PAGES = 100
_INTER_MARKETPLACE_DELAY = 2.0
_API_QUOTA_LIMIT = 4_500


@ServiceRegistry.register(
    path="integrations.ebay.category_sweep",
    db_repositories=["ebay_sales", "ebay_scrape"],
    api_repositories=["ebay_finding"],
    runs_in_transaction=False,
)
async def ebay_category_sweep(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    **kwargs: Any,
) -> dict:
    """Daily category sweep: fetch all MTG sold items, title-match to known eBay cards."""
    settings = get_settings()
    app_id = getattr(settings, "ebay_app_id", None)
    if not app_id:
        logger.warning("ebay_category_sweep_no_app_id")
        return {"fetched": 0, "matched": 0, "inserted": 0}

    lookup_rows = await ebay_sales_repository.get_ebay_card_lookup()
    if not lookup_rows:
        logger.info("ebay_category_sweep_no_cards_in_lookup")
        return {"fetched": 0, "matched": 0, "inserted": 0}

    card_lookup: dict[int, dict] = {r["source_product_id"]: r for r in lookup_rows}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    redis_host = getattr(settings, "redis_host", "localhost")
    redis_port = getattr(settings, "redis_port", 6379)
    redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}/0")

    totals = {"fetched": 0, "matched": 0, "inserted": 0}
    try:
        for marketplace in _MARKETPLACES:
            result = await _sweep_marketplace(
                marketplace=marketplace,
                today=today,
                app_id=app_id,
                card_lookup=card_lookup,
                ebay_finding_repository=ebay_finding_repository,
                ebay_scrape_repository=ebay_scrape_repository,
                redis_client=redis_client,
            )
            for k in totals:
                totals[k] += result[k]
            await asyncio.sleep(_INTER_MARKETPLACE_DELAY)
    finally:
        await redis_client.aclose()

    logger.info("ebay_category_sweep_complete", extra=totals)
    return totals


async def _sweep_marketplace(
    marketplace: str,
    today: str,
    app_id: str,
    card_lookup: dict[int, dict],
    ebay_finding_repository: EbayFindingAPIRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    redis_client,
) -> dict:
    path = sweep_path(today, marketplace)
    items, was_cached, was_corrupt = load_or_fetch_items(path)
    if was_cached:
        logger.info(
            "ebay_category_sweep_replay",
            extra={"marketplace": marketplace, "items": len(items)},
        )
    else:
        if was_corrupt:
            logger.warning("ebay_category_sweep_corrupt_file", extra={"path": str(path)})
        items = await _fetch_and_stage(
            path, marketplace, app_id, ebay_finding_repository, redis_client, today
        )

    fetched = len(items)
    matched = 0
    inserted = 0

    for item in items:
        best_spid = _match_item(item, card_lookup)
        if best_spid is None:
            continue
        matched += 1
        ok = await _insert_matched(item, best_spid, marketplace, ebay_scrape_repository)
        if ok:
            inserted += 1

    logger.info(
        "ebay_category_sweep_marketplace_done",
        extra={
            "marketplace": marketplace,
            "fetched": fetched,
            "matched": matched,
            "inserted": inserted,
        },
    )
    return {"fetched": fetched, "matched": matched, "inserted": inserted}


async def _fetch_and_stage(
    path, marketplace, app_id, finding_repo, redis_client, today
) -> list[dict]:
    if await quota_remaining(redis_client, today, _API_QUOTA_LIMIT) == 0:
        logger.warning(
            "ebay_category_sweep_quota_exhausted",
            extra={"marketplace": marketplace, "today": today},
        )
        return []

    async def _on_page():
        await quota_increment(redis_client, today)

    items = await finding_repo.find_completed_items(
        keywords=None,
        app_id=app_id,
        global_id=marketplace,
        max_pages=_SWEEP_MAX_PAGES,
        on_page_fetched=_on_page,
    )

    try:
        write_items_to_json(path, items, marketplace, source_product_id=None)
    except OSError:
        logger.error("ebay_category_sweep_write_failed", extra={"path": str(path)})

    return items


def _match_item(item: dict, card_lookup: dict[int, dict]) -> Optional[int]:
    title = item.get("title", "")
    best_spid: Optional[int] = None
    best_score = 0.0

    for spid, card in card_lookup.items():
        sc = score_title(
            title, card["card_name"], card.get("set_code"), is_foil=None, frame=None
        )
        if sc > best_score:
            best_score = sc
            best_spid = spid

    return best_spid if best_score >= _SCORE_THRESHOLD else None


async def _insert_matched(
    item: dict,
    source_product_id: int,
    marketplace: str,
    ebay_scrape_repository: EbayScrapeSoldRepository,
) -> bool:
    item_id = item.get("item_id", "")
    title = item.get("title", "")
    sold_date = item.get("sold_date")
    price_raw = item.get("price")

    if not item_id or not sold_date or price_raw is None:
        return False

    price_cents = to_cents(price_raw)
    if price_cents is None:
        return False

    sold_at = parse_sold_date(sold_date)

    finish_code = parse_finish_code(title)
    condition_code = parse_condition_code(item.get("condition"), title)

    try:
        await ebay_scrape_repository.insert_scraped_sold(
            item_id=item_id,
            title=title,
            source_product_id=source_product_id,
            price_cents=price_cents,
            currency=item.get("currency", "USD"),
            marketplace_id=marketplace,
            condition_id=CONDITION_ID_MAP.get(condition_code, 1),
            finish_id=FINISH_ID_MAP.get(finish_code, 1),
            language_id=_DEFAULT_LANGUAGE_ID,
            sold_at=sold_at,
        )
        return True
    except Exception:
        logger.warning(
            "ebay_category_sweep_insert_failed", extra={"item_id": item_id}
        )
        return False
