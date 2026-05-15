from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
from datetime import date
from uuid import UUID


class DateRange(BaseModel):
    """Date range information for price history query."""
    start: date = Field(..., description="Start date")
    end: date = Field(..., description="End date")
    days_back: Optional[int] = Field(default=None, description="Days back from today (None for full history)")


class CardPriceEntry(BaseModel):
    """One price point for a card (source × finish × condition × language)."""
    model_config = ConfigDict(from_attributes=True)

    source: str = Field(..., description="Price source code (e.g. tcg, cardmarket)")
    finish: str = Field(..., description="Card finish code (e.g. NONFOIL, FOIL)")
    condition: str = Field(..., description="Condition code (e.g. NM, LP)")
    language: str = Field(..., description="Language code (e.g. en, jp)")
    price_date: date = Field(..., description="Date of the price observation")
    market_cents: Optional[int] = Field(None, description="Market price in cents")
    low_cents: Optional[int] = Field(None, description="Low price in cents")


class CardPricesResponse(BaseModel):
    """Current prices and marketplace buy links for a card version."""
    model_config = ConfigDict(from_attributes=True)

    card_version_id: UUID
    purchase_uris: Optional[Dict[str, Any]] = Field(
        None, description="Marketplace buy links keyed by vendor (e.g. tcgplayer, cardmarket)"
    )
    prices: List[CardPriceEntry] = Field(default_factory=list)


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
