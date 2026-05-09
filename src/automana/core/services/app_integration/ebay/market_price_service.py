import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from automana.core.models.ebay.market_price import CardMarketData, PriceAggregates, PricePoint
from automana.core.repositories.app_integration.ebay.ApiBrowse_repository import EbayBrowseAPIRepository
from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_app_token
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)

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

        shipping_cost: Optional[float] = None
        shipping_options = item.get("shippingOptions", [])
        if shipping_options:
            try:
                shipping_cost = float(shipping_options[0].get("shippingCost", {}).get("value", 0))
            except (TypeError, ValueError):
                shipping_cost = None

        item_country: Optional[str] = item.get("itemLocation", {}).get("country") or None

        ships_to_au: Optional[bool] = None
        ship_to = item.get("shipToLocations", {})
        included = ship_to.get("regionIncluded", [])
        excluded = ship_to.get("regionExcluded", [])
        if included:
            ships = any(
                r.get("regionType") == "WORLDWIDE" or r.get("regionId") == "AU"
                for r in included
            )
            if ships and any(r.get("regionId") == "AU" for r in excluded):
                ships = False
            ships_to_au = ships

        points.append(
            PricePoint(
                item_id=item.get("itemId", ""),
                title=item.get("title", ""),
                price=price,
                currency=price_block.get("currency", ""),
                shipping_cost=shipping_cost,
                condition=item.get("condition"),
                url=item.get("itemWebUrl"),
                sold_date=None,
                item_country=item_country,
                ships_to_au=ships_to_au,
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
    api_repositories=["search"],
    runs_in_transaction=False,
)
async def fetch_card_market_price(
    auth_repository: EbayAuthRepository,
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
    match_threshold: float = 0.3,
    marketplace_id: str = "EBAY_AU",
    **kwargs,
) -> CardMarketData:
    app_settings = await auth_repository.get_app_settings(app_code=app_code, user_id=user_id)
    if not app_settings:
        raise ValueError(f"No eBay app found for app_code={app_code!r}")

    env = app_settings["environment"].lower()
    if env != search_repository.environment:
        search_repository.environment = env
        search_repository.base_url = search_repository._get_base_url()

    # App token (client credentials) is required for Browse API public search.
    # The eBay Finding API was decommissioned Feb 2025; sold data is unavailable.
    app_token = await resolve_app_token(app_settings)

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
        "Authorization": f"Bearer {app_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
    }

    sold_raw: list[dict] = []
    active_raw: dict = {}

    try:
        active_raw = await search_repository.search_items(browse_params, headers=browse_headers)
    except Exception as exc:
        logger.warning("Browse API failed; returning empty active list", extra={"error": str(exc)})

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
