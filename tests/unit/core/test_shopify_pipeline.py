import pytest
from automana.core.repositories.app_integration.shopify.pipeline_repository import (
    _map_variation,
)


@pytest.mark.parametrize("variation,expected_condition,expected_finish", [
    ("Near Mint",             "NM",  "nonfoil"),
    ("Near Mint Foil",        "NM",  "foil"),
    ("Lightly Played",        "LP",  "nonfoil"),
    ("Lightly Played Foil",   "LP",  "foil"),
    ("Slightly Played",       "LP",  "nonfoil"),
    ("Slightly Played Foil",  "LP",  "foil"),
    ("Moderately Played",     "MP",  "nonfoil"),
    ("Moderately Played Foil","MP",  "foil"),
    ("Heavily Played",        "HP",  "nonfoil"),
    ("Heavily Played Foil",   "HP",  "foil"),
    ("Damaged",               "DMG", "nonfoil"),
    ("Damaged Foil",          "DMG", "foil"),
])
def test_map_variation(variation, expected_condition, expected_finish):
    condition_code, finish_code = _map_variation(variation)
    assert condition_code == expected_condition
    assert finish_code == expected_finish


def test_map_variation_unknown_defaults_to_nm_nonfoil():
    condition_code, finish_code = _map_variation("Unknown Grade")
    assert condition_code == "NM"
    assert finish_code == "nonfoil"


from decimal import Decimal
from automana.core.services.app_integration.shopify.pipeline_service import (
    _price_to_cents,
    _build_obs_dataframe,
)


def test_price_to_cents_rounds_correctly():
    assert _price_to_cents(Decimal("4.99")) == 499
    assert _price_to_cents(Decimal("10.00")) == 1000
    assert _price_to_cents(Decimal("0.50")) == 50
    assert _price_to_cents(None) is None
    assert _price_to_cents(Decimal("4.995")) == 500  # rounds up, not truncates


def test_build_obs_dataframe_excludes_unmapped_rows():
    refs = {
        "sell_type_id": 1,
        "data_provider_id": 5,
        "language_id": 1,
        "conditions": {"NM": 1, "LP": 2},
        "finishes": {"nonfoil": 1, "foil": 2},
    }
    staging_rows = [
        {"product_id": 100, "date": "2026-05-18", "variation": "Near Mint",
         "price": Decimal("4.99"), "scraped_at": "2026-05-18", "tcg_id": 999, "source_id": 3},
        {"product_id": 101, "date": "2026-05-18", "variation": "Near Mint Foil",
         "price": Decimal("9.99"), "scraped_at": "2026-05-18", "tcg_id": None, "source_id": 3},
    ]
    tcg_to_cv = {999: "aaaaaaaa-0000-0000-0000-000000000001"}
    cv_to_sp = {"aaaaaaaa-0000-0000-0000-000000000001": 42}

    df = _build_obs_dataframe(staging_rows, tcg_to_cv, cv_to_sp, refs)
    assert len(df) == 1
    assert df.iloc[0]["source_product_id"] == 42
    assert df.iloc[0]["list_avg_cents"] == 499
    assert df.iloc[0]["finish_id"] == 1
    assert df.iloc[0]["condition_id"] == 1


def test_build_obs_dataframe_empty_staging():
    refs = {
        "sell_type_id": 1, "data_provider_id": 5, "language_id": 1,
        "conditions": {"NM": 1}, "finishes": {"nonfoil": 1, "foil": 2},
    }
    df = _build_obs_dataframe([], {}, {}, refs)
    assert df.empty


def test_build_obs_dataframe_all_columns_present():
    refs = {
        "sell_type_id": 1, "data_provider_id": 5, "language_id": 1,
        "conditions": {"NM": 1}, "finishes": {"nonfoil": 1, "foil": 2},
    }
    staging_rows = [
        {"product_id": 100, "date": "2026-05-18", "variation": "Near Mint",
         "price": Decimal("5.00"), "scraped_at": "2026-05-18", "tcg_id": 1, "source_id": 3},
    ]
    df = _build_obs_dataframe(staging_rows, {1: "uuid-1"}, {"uuid-1": 99}, refs)
    expected_cols = {
        "ts_date", "price_type_id", "finish_id", "condition_id", "language_id",
        "list_low_cents", "list_avg_cents", "sold_avg_cents", "list_count",
        "sold_count", "source_product_id", "data_provider_id", "scraped_at",
    }
    assert set(df.columns) == expected_cols
    assert df.iloc[0]["list_avg_cents"] == 500


def test_map_variation_case_insensitive():
    condition, finish = _map_variation("NEAR MINT FOIL")
    assert condition == "NM"
    assert finish == "foil"
