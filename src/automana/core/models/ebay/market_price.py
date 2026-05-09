import statistics
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class PricePoint(BaseModel):
    item_id: str
    title: str
    price: float
    currency: str
    shipping_cost: Optional[float] = None
    condition: Optional[str] = None
    url: Optional[str] = None
    sold_date: Optional[datetime] = None
    relevance_score: float = 0.0
    item_country: Optional[str] = None
    ships_to_au: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class PriceAggregates(BaseModel):
    count: int
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_prices(cls, prices: list[float]) -> "PriceAggregates":
        if not prices:
            return cls(count=0)
        sorted_prices = sorted(prices)
        p25: Optional[float] = None
        p75: Optional[float] = None
        if len(sorted_prices) >= 4:
            qs = statistics.quantiles(sorted_prices, n=4, method="inclusive")
            p25 = round(qs[0], 2)
            p75 = round(qs[2], 2)
        return cls(
            count=len(prices),
            min=round(sorted_prices[0], 2),
            max=round(sorted_prices[-1], 2),
            mean=round(statistics.mean(prices), 2),
            median=round(statistics.median(prices), 2),
            p25=p25,
            p75=p75,
        )


class CardMarketData(BaseModel):
    query: str
    card_name: str
    set_code: Optional[str] = None
    condition_id: Optional[int] = None
    is_foil: Optional[bool] = None
    frame: Optional[str] = None
    as_of: datetime
    sold: list[PricePoint] = []
    active: list[PricePoint] = []
    sold_aggregates: PriceAggregates
    active_aggregates: PriceAggregates
    suggested_price: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True)
