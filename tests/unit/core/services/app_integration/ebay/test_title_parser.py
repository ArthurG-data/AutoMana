import pytest
from automana.core.services.app_integration.ebay.title_parser import (
    parse_finish_code,
    parse_condition_code,
    FINISH_ID_MAP,
    CONDITION_ID_MAP,
)


# --- parse_finish_code ---

@pytest.mark.parametrize("title,expected", [
    ("Sheoldred the Apocalypse Surge Foil NM MH2", "SURGE_FOIL"),
    ("Sheoldred Ripple Foil NM MH2 MTG", "RIPPLE_FOIL"),
    ("Sheoldred Rainbow Foil NM MH2", "RAINBOW_FOIL"),
    ("Sheoldred Etched Foil NM MH2", "ETCHED"),
    ("Sheoldred Foil Etched NM MH2", "ETCHED"),
    ("Sheoldred Foil NM MH2 MTG", "FOIL"),
    ("Sheoldred NM MH2 MTG", "NONFOIL"),
    ("Sheoldred Non-Foil NM MH2 MTG", "NONFOIL"),
    ("Sheoldred Nonfoil NM MH2 MTG", "NONFOIL"),
    ("SHEOLDRED FOIL NM MH2", "FOIL"),          # case insensitive
])
def test_parse_finish_code(title, expected):
    assert parse_finish_code(title) == expected


# --- parse_condition_code ---

@pytest.mark.parametrize("ebay_cond,title,expected", [
    ("Near Mint or Better", "", "NM"),
    ("Lightly Played", "", "LP"),
    ("Moderately Played", "", "MP"),
    ("Heavily Played", "", "HP"),
    ("Damaged", "", "DMG"),
    (None, "Sheoldred NM Foil MH2", "NM"),
    (None, "Sheoldred LP Showcase MH2", "LP"),
    (None, "Sheoldred SP MH2 MTG", "SP"),
    (None, "Sheoldred MP MH2 MTG", "MP"),
    (None, "Sheoldred HP MH2 MTG", "HP"),
    (None, "Sheoldred PLD MH2 MTG", "HP"),
    (None, "Sheoldred Damaged MH2", "DMG"),
    (None, "Sheoldred MTG card no condition", "NM"),   # default
    ("", "Sheoldred MTG card no condition", "NM"),     # empty ebay string → default
])
def test_parse_condition_code(ebay_cond, title, expected):
    assert parse_condition_code(ebay_cond, title) == expected


# --- ID maps are complete ---

def test_finish_id_map_covers_all_codes():
    for code in ("NONFOIL", "FOIL", "ETCHED", "SURGE_FOIL", "RIPPLE_FOIL", "RAINBOW_FOIL"):
        assert code in FINISH_ID_MAP

def test_condition_id_map_covers_all_codes():
    for code in ("NM", "LP", "SP", "MP", "HP", "DMG"):
        assert code in CONDITION_ID_MAP
