import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from automana.core.models.ebay.market_price import CardMarketData, PriceAggregates, PricePoint
from automana.core.repositories.app_integration.ebay.ApiFinding_repository import EbayFindingAPIRepository
from automana.core.repositories.app_integration.ebay.ApiBrowse_repository import EbayBrowseAPIRepository
from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)
from automana.core.settings import get_settings

logger = logging.getLogger(__name__)

_MTG_CATEGORY_ID = 2536


def _finding_items_to_price_points(raw_items: list[dict]) -> list[PricePoint]:
    points = []
    for item in raw_items:
        sold_date = None
        raw_date = item.get("sold_date")
        if raw_date:
            try:
                sold_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        points.append(
            PricePoint(
                item_id=item.get("item_id", ""),
                title=item.get("title", ""),
                price=float(item.get("price", 0)),
                currency=item.get("currency", ""),
                condition=item.get("condition"),
                url=item.get("url"),
                sold_date=sold_date,
            )
        )
    return points


def _browse_items_to_price_points(raw_data: dict) -> list[PricePoint]:
    points = []
    for item in raw_data.get("itemSummaries", []):
        price_block = item.get("price", {})
        try:
            price = float(price_block.get("value", 0))
        except (TypeError, ValueError):
            price = 0.0
        points.append(
            PricePoint(
                item_id=item.get("itemId", ""),
                title=item.get("title", ""),
                price=price,
                currency=price_block.get("currency", ""),
                condition=item.get("condition"),
                url=item.get("itemWebUrl"),
                sold_date=None,
            )
        )
    return points


def _score_and_filter(
    points: list[PricePoint],
    card_name: str,
    set_code: Optional[str],
    is_foil: Optional[bool],
    frame: Optional[str],
    threshold: float,
) -> list[PricePoint]:
    scored = []
    for p in points:
        s = score_title(p.title, card_name, set_code, is_foil, frame)
        if s >= threshold:
            scored.append(p.model_copy(update={"relevance_score": s}))
    return sorted(scored, key=lambda x: x.relevance_score, reverse=True)


@ServiceRegistry.register(
    path="integrations.ebay.market_price",
    db_repositories=["auth"],
    api_repositories=["ebay_finding", "search"],
    runs_in_transaction=False,
)
async def fetch_card_market_price(
    auth_repository: EbayAuthRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    search_repository: EbayBrowseAPIRepository,
    card_name: str,
    user_id: UUID,
    app_code: str,
    set_code: Optional[str] = None,
    condition_id: Optional[int] = None,
    is_foil: Optional[bool] = None,
    frame: Optional[str] = None,
    days_back: int = 30,
    limit: int = 50,
    match_threshold: float = 0.6,
    **kwargs,
) -> CardMarketData:
    settings = get_settings()
    if not settings.ebay_app_id:
        raise ValueError("ebay_app_id is not configured; cannot call Finding API")
    app_id = settings.ebay_app_id

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)

    raw_env = await auth_repository.get_environment(app_code=app_code)
    if raw_env:
        env = raw_env.lower()
        ebay_finding_repository.environment = env
        search_repository.environment = env

    logger.info(
        "ebay_fetch_card_market_price_requested",
        extra={
            "card_name": card_name,
            "set_code": set_code,
            "condition_id": condition_id,
            "is_foil": is_foil,
            "frame": frame,
            "days_back": days_back,
            "limit": limit,
        },
    )

    query = build_query_string(card_name, set_code, is_foil, frame)
    min_date = datetime.now(timezone.utc) - timedelta(days=min(days_back, 90))
    sold_limit = min(limit, 100)
    active_limit = min(limit, 200)

    browse_params = {
        "q": query,
        "category_ids": [str(_MTG_CATEGORY_ID)],
        "limit": active_limit,
        "offset": 0,
    }
    if condition_id is not None:
        browse_params["filter"] = [f"conditionIds:{{{condition_id}}}"]

    browse_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    sold_raw: list[dict] = []
    active_raw: dict = {}

    async def _fetch_sold() -> list[dict]:
        return await ebay_finding_repository.find_completed_items(
            keywords=query,
            app_id=app_id,
            category_id=_MTG_CATEGORY_ID,
            condition_id=condition_id,
            min_date=min_date,
            limit=sold_limit,
        )

    async def _fetch_active() -> dict:
        return await search_repository.search_items(browse_params, headers=browse_headers)

    results = await asyncio.gather(_fetch_sold(), _fetch_active(), return_exceptions=True)

    if isinstance(results[0], BaseException):
        logger.warning("Finding API failed; returning empty sold list", extra={"error": str(results[0])})
    else:
        sold_raw = results[0]

    if isinstance(results[1], BaseException):
        logger.warning("Browse API failed; returning empty active list", extra={"error": str(results[1])})
    else:
        active_raw = results[1]

    sold_points = _score_and_filter(
        _finding_items_to_price_points(sold_raw),
        card_name, set_code, is_foil, frame, match_threshold,
    )
    active_points = _score_and_filter(
        _browse_items_to_price_points(active_raw),
        card_name, set_code, is_foil, frame, match_threshold,
    )

    sold_agg = PriceAggregates.from_prices([p.price for p in sold_points])
    active_agg = PriceAggregates.from_prices([p.price for p in active_points])

    suggested_price = sold_agg.median if sold_agg.count >= 3 else None

    return CardMarketData(
        query=query,
        card_name=card_name,
        set_code=set_code,
        condition_id=condition_id,
        is_foil=is_foil,
        frame=frame,
        as_of=datetime.now(timezone.utc),
        sold=sold_points,
        active=active_points,
        sold_aggregates=sold_agg,
        active_aggregates=active_agg,
        suggested_price=suggested_price,
    )
