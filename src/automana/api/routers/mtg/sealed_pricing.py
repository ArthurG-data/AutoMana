"""Sealed product pricing API endpoints."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from automana.api.dependancies.service_deps import ServiceManagerDep

logger = logging.getLogger(__name__)


class SealedPriceRow(BaseModel):
    product_id: str
    name: str
    product_type: str
    mtgjson_uuid: str
    source: str
    transaction_type: str
    price_date: Optional[date]
    list_low_cents: Optional[int]
    list_avg_cents: Optional[int]
    sold_avg_cents: Optional[int]


class SealedPricesResponse(BaseModel):
    set_code: str
    prices: list[SealedPriceRow]


class SealedPriceHistoryRow(BaseModel):
    ts_date: date
    source: str
    transaction_type: str
    list_avg_cents: Optional[int]
    sold_avg_cents: Optional[int]


class SealedPriceHistoryResponse(BaseModel):
    mtgjson_uuid: str
    history: list[SealedPriceHistoryRow]


sealed_pricing_router = APIRouter(
    prefix="/sealed",
    tags=["Sealed Pricing"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
    },
)


@sealed_pricing_router.get(
    "/{set_code}/prices",
    summary="Current sealed prices for a set",
    response_model=SealedPricesResponse,
    operation_id="sealed_prices_by_set",
)
async def get_sealed_prices_by_set(
    set_code: str,
    service_manager: ServiceManagerDep,
) -> SealedPricesResponse:
    try:
        rows = await service_manager.execute_service(
            "pricing.sealed.get_prices_by_set",
            set_code=set_code,
        )
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No sealed products found for set '{set_code}'",
            )
        prices = [
            SealedPriceRow(**{**r, "product_id": str(r["product_id"])})
            for r in rows
        ]
        return SealedPricesResponse(set_code=set_code, prices=prices)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error fetching sealed prices by set",
            extra={"set_code": set_code, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")


@sealed_pricing_router.get(
    "/{set_code}/{mtgjson_uuid}/history",
    summary="Daily price history for a sealed product",
    response_model=SealedPriceHistoryResponse,
    operation_id="sealed_price_history",
)
async def get_sealed_price_history(
    set_code: str,
    mtgjson_uuid: str,
    service_manager: ServiceManagerDep,
    from_date: Optional[date] = Query(None, description="Start of date range (inclusive)"),
    to_date: Optional[date] = Query(None, description="End of date range (inclusive)"),
    source: Optional[str] = Query(None, description="Filter by price source code (e.g. 'tcg')"),
) -> SealedPriceHistoryResponse:
    try:
        rows = await service_manager.execute_service(
            "pricing.sealed.get_price_history",
            mtgjson_uuid=mtgjson_uuid,
            from_date=from_date or date(2020, 1, 1),
            to_date=to_date or date.today(),
        )
        if source:
            rows = [r for r in rows if r["source"] == source]
        history = [SealedPriceHistoryRow.model_validate(r) for r in rows]
        return SealedPriceHistoryResponse(mtgjson_uuid=mtgjson_uuid, history=history)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error fetching sealed price history",
            extra={"mtgjson_uuid": mtgjson_uuid, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")
