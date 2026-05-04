from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import date


class DateRange(BaseModel):
    """Date range information for price history query."""
    start: date = Field(..., description="Start date")
    end: date = Field(..., description="End date")
    days_back: Optional[int] = Field(default=None, description="Days back from today (None for full history)")


class PriceHistoryResponse(BaseModel):
    """Aggregated daily price history for a card."""
    model_config = ConfigDict(from_attributes=True)

    price_history_list_avg: Optional[List[Optional[float]]] = Field(
        default=None,
        description="Daily list average prices in dollars (oldest to newest, dense: one per calendar day, null for missing dates)."
    )
    price_history_sold_avg: Optional[List[Optional[float]]] = Field(
        default=None,
        description="Daily sold average prices in dollars (oldest to newest, dense: one per calendar day, null for missing dates)."
    )
    date_range: DateRange = Field(..., description="Date range covered by this history")
