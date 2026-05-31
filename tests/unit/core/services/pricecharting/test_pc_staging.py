"""Unit tests for the pure PriceCharting staging helpers."""
from datetime import datetime, timezone

import pytest

from automana.core.services.app_integration.pricecharting import pc_staging as s


# ── parse_condition ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("title,grade,cid", [
    ("Ragavan Near Mint English", "ungraded", 1),
    ("Card LP", "ungraded", 2),
    ("Card moderately played", "ungraded", 3),
    ("Card HP", "ungraded", 4),
    ("Card damaged", "ungraded", 5),
    ("No condition mentioned", "ungraded", 1),     # NM default
    ("PSA 10 slab", "psa10", 10),                   # graded maps by grade label
    ("graded copy", "grade9", 9),
    ("unknown grade label", "gradeX", 1),           # unknown graded -> default 1
])
def test_parse_condition(title, grade, cid):
    assert s.parse_condition(title, grade) == cid


# ── marketplace_for_source ───────────────────────────────────────────────────
@pytest.mark.parametrize("source,mkt", [
    ("ebay", "EBAY-US"),
    ("tcgplayer", "TCGPLAYER"),
    ("unknown", "PRICECHARTING"),
])
def test_marketplace_for_source(source, mkt):
    assert s.marketplace_for_source(source) == mkt


# ── parse_sold_at ────────────────────────────────────────────────────────────
def test_parse_sold_at_adds_utc():
    dt = s.parse_sold_at("2026-05-30")
    assert dt == datetime(2026, 5, 30, tzinfo=timezone.utc)


def test_parse_sold_at_invalid_returns_none():
    assert s.parse_sold_at("not a date") is None
    assert s.parse_sold_at(None) is None


# ── build_item_id ────────────────────────────────────────────────────────────
def test_build_item_id_deterministic_and_prefixed():
    dt = datetime(2026, 5, 30, tzinfo=timezone.utc)
    a = s.build_item_id("2254550", dt, 4538, "Ragavan NM")
    b = s.build_item_id("2254550", dt, 4538, "Ragavan NM")
    assert a == b
    assert a.startswith("pc-") and len(a) == len("pc-") + 12


def test_build_item_id_varies_with_inputs():
    dt = datetime(2026, 5, 30, tzinfo=timezone.utc)
    base = s.build_item_id("2254550", dt, 4538, "Ragavan NM")
    assert s.build_item_id("2254550", dt, 9999, "Ragavan NM") != base   # price
    assert s.build_item_id("9999999", dt, 4538, "Ragavan NM") != base   # product


# ── build_accepted_sales ─────────────────────────────────────────────────────
@pytest.fixture
def catalog():
    return {
        "2254550": {"card_version_id": "cv-138", "finish_id": 1, "collector_number": "138"},
        "6659865": {"card_version_id": "cv-138f", "finish_id": 2, "collector_number": "138"},
        "0000000": None,   # unmatched
    }


def test_build_accepted_sales_joins_and_parses(catalog):
    sales_products = {
        "2254550": {"tcgplayer_id": "239857", "sales": [
            {"grade": "ungraded", "sold_at": "2026-05-30", "title": "Ragavan NM", "price_cents": 4538, "source": "tcgplayer"},
            {"grade": "grade9", "sold_at": "2026-05-29", "title": "Ragavan PSA 9", "price_cents": 12000, "source": "ebay"},
        ]},
        "0000000": {"sales": [   # unmatched product -> all dropped
            {"grade": "ungraded", "sold_at": "2026-05-30", "title": "x", "price_cents": 100, "source": "ebay"},
        ]},
    }
    out = s.build_accepted_sales(sales_products, catalog)
    assert len(out) == 2

    nm = next(r for r in out if r["condition_id"] == 1)
    assert nm["card_version_id"] == "cv-138"
    assert nm["finish_id"] == 1
    assert nm["marketplace_id"] == "TCGPLAYER"
    assert nm["language_id"] == 1
    assert nm["currency"] == "USD"
    assert nm["sold_at"] == datetime(2026, 5, 30, tzinfo=timezone.utc)

    graded = next(r for r in out if r["condition_id"] == 9)
    assert graded["price_cents"] == 12000
    assert graded["marketplace_id"] == "EBAY-US"


def test_build_accepted_sales_drops_unparseable_date_and_null_price(catalog):
    sales_products = {
        "2254550": {"sales": [
            {"grade": "ungraded", "sold_at": "garbage", "title": "x", "price_cents": 100, "source": "ebay"},
            {"grade": "ungraded", "sold_at": "2026-05-30", "title": "y", "price_cents": None, "source": "ebay"},
            {"grade": "ungraded", "sold_at": "2026-05-30", "title": "z", "price_cents": 500, "source": "ebay"},
        ]},
    }
    out = s.build_accepted_sales(sales_products, catalog)
    assert len(out) == 1
    assert out[0]["title"] == "z"


def test_build_accepted_sales_empty():
    assert s.build_accepted_sales({}, {}) == []
