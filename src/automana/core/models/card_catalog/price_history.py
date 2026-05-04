from pydantic import BaseModel, Field
from typing import List, Optional


class DateRange(BaseModel):
    """Date range information for price history query."""
    start: str = Field(..., description="Start date (YYYY-MM-DD)")
    end: str = Field(..., description="End date (YYYY-MM-DD)")
    days_back: Optional[int] = Field(default=None, description="Days back from today (None for all)")


class PriceHistoryResponse(BaseModel):
    """Aggregated daily price history for a card."""
    price_history_list_avg: Optional[List[float]] = Field(
        default=None,
        description="Daily list average prices in dollars (oldest to newest, one per day)."
    )
    price_history_sold_avg: Optional[List[float]] = Field(
        default=None,
        description="Daily sold average prices in dollars (oldest to newest, one per day)."
    )
    date_range: DateRange = Field(..., description="Date range covered by this history")
