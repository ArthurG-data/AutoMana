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
