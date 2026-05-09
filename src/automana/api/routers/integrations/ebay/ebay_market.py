from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from automana.api.dependancies.auth.users import CurrentUserDep
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.core.models.ebay.market_price import CardMarketData

market_router = APIRouter(prefix="/market-price", tags=["eBay Market Price"])


@market_router.get("/", response_model=CardMarketData)
async def get_market_price(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    card_name: str = Query(..., description="Card name, e.g. 'Sheoldred, the Apocalypse'"),
    app_code: str = Query(..., description="eBay app code for OAuth token resolution"),
    set_code: Optional[str] = Query(None, description="Set code, e.g. 'DMR'"),
    condition_id: Optional[int] = Query(None, description="eBay condition ID (3000=NM, 4000=LP)"),
    is_foil: Optional[bool] = Query(None, description="Foil or non-foil"),
    frame: Optional[str] = Query(None, description="Frame variant: showcase, extended_art, borderless, normal"),
    days_back: int = Query(30, ge=1, le=90, description="Lookback window for sold items"),
    limit: int = Query(50, ge=1, le=200, description="Max results per source"),
    match_threshold: float = Query(0.3, ge=0.0, le=1.0, description="Minimum relevance score (0–1)"),
) -> CardMarketData:
    try:
        result: CardMarketData = await service_manager.execute_service(
            "integrations.ebay.market_price",
            user_id=user.unique_id,
            app_code=app_code,
            card_name=card_name,
            set_code=set_code,
            condition_id=condition_id,
            is_foil=is_foil,
            frame=frame,
            days_back=days_back,
            limit=limit,
            match_threshold=match_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result
