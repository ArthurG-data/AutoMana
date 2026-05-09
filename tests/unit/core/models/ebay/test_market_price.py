from datetime import datetime, timezone
from automana.core.models.ebay.market_price import PriceAggregates, PricePoint, CardMarketData


def test_price_aggregates_empty():
    agg = PriceAggregates.from_prices([])
    assert agg.count == 0
    assert agg.min is None
    assert agg.median is None


def test_price_aggregates_single():
    agg = PriceAggregates.from_prices([10.0])
    assert agg.count == 1
    assert agg.min == 10.0
    assert agg.max == 10.0
    assert agg.mean == 10.0
    assert agg.median == 10.0
    assert agg.p25 is None  # not enough data for quartiles
    assert agg.p75 is None


def test_price_aggregates_known_values():
    # prices: 1, 2, 3, 4, 5 → median=3, mean=3, p25=2, p75=4
    agg = PriceAggregates.from_prices([5.0, 1.0, 3.0, 2.0, 4.0])
    assert agg.count == 5
    assert agg.min == 1.0
    assert agg.max == 5.0
    assert agg.median == 3.0
    assert agg.mean == 3.0
    assert agg.p25 == 2.0
    assert agg.p75 == 4.0


def test_price_point_defaults():
    pp = PricePoint(
        item_id="123",
        title="Sheoldred",
        price=45.0,
        currency="AUD",
        relevance_score=0.8,
    )
    assert pp.sold_date is None
    assert pp.condition is None
    assert pp.url is None


def test_card_market_data_structure():
    now = datetime.now(timezone.utc)
    agg = PriceAggregates.from_prices([10.0, 20.0, 30.0, 40.0, 50.0])
    data = CardMarketData(
        query="Sheoldred DMR MTG",
        card_name="Sheoldred, the Apocalypse",
        set_code="DMR",
        condition_id=3000,
        is_foil=False,
        frame=None,
        as_of=now,
        sold=[],
        active=[],
        sold_aggregates=agg,
        active_aggregates=PriceAggregates.from_prices([]),
        suggested_price=30.0,
    )
    assert data.card_name == "Sheoldred, the Apocalypse"
    assert data.sold_aggregates.median == 30.0
