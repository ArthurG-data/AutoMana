import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import automana.core.services.app_integration.ebay.price_trend_service  # noqa: F401  — registers 'integrations.ebay.recommendations.trend'
from automana.api.dependancies.auth.users import CurrentUserDep
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import ApiResponse

logger = logging.getLogger(__name__)


class RecommendationRequest(BaseModel):
    days_listed: int
    watch_count: int
    price: float
    currency: str = "AUD"
    market_data: Optional[dict] = None


class StageActionRequest(BaseModel):
    action_type: Literal["raise", "lower", "hold", "draft"]
    strategy_kind: str
    suggested_price: Optional[float] = None


router = APIRouter()


@router.post("/{item_id}", description="Get a pricing recommendation for an eBay listing")
async def get_recommendation(
    item_id: str,
    body: RecommendationRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.recommendations.get",
            user_id=user.unique_id,
            app_code=app_code,
            item_id=item_id,
            **body.model_dump(),
        )
        return ApiResponse(message="Recommendation retrieved", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise


@router.post("/{item_id}/stage", description="Stage a pricing action for an eBay listing")
async def stage_action(
    item_id: str,
    body: StageActionRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.actions.stage",
            user_id=user.unique_id,
            app_code=app_code,
            item_id=item_id,
            **body.model_dump(),
        )
        return ApiResponse(
            message="Action staged successfully",
            data={"action_id": result.get("action_id"), "created": result.get("created")},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise


@router.get("/{item_id}/pending", description="Check for a pending action on an eBay listing")
async def get_pending_action(
    item_id: str,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.actions.get_pending",
            item_id=item_id,
        )
        if result is None:
            return ApiResponse(message="No pending action", data={"pending": None})
        return ApiResponse(message="Pending action found", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise


@router.get("/{item_id}/trend", description="Get historical price trend and recommendation for an active eBay listing")
async def get_listing_price_trend(
    item_id: str,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.recommendations.trend",
            item_id=item_id,
            app_code=app_code,
        )
        return ApiResponse(message="Price trend retrieved", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise
