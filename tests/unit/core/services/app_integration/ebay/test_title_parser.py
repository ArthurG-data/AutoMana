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
    ("Sheoldred Etched NM MH2", "ETCHED"),     # bare etched without foil word
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


from automana.core.services.app_integration.ebay.title_parser import (
    parse_frame_variant,
    conflicts_with_expected,
)


# --- parse_frame_variant ---

@pytest.mark.parametrize("title,expected_key,expected_val", [
    ("Sheoldred Showcase Foil NM MH2",   "frame_effects",  ["showcase"]),
    ("Sheoldred Extended Art NM MH2",    "frame_effects",  ["extendedart"]),
    ("Sheoldred Ext Art NM MH2",         "frame_effects",  ["extendedart"]),
    ("Sheoldred EA NM MH2",              "frame_effects",  ["extendedart"]),
    ("Sheoldred Borderless NM MH2",      "is_borderless",  True),
    ("Sheoldred Retro Frame NM MH2",     "frame_effects",  ["retro"]),
    ("Sheoldred Old Border NM MH2",      "frame_effects",  ["retro"]),
    ("Sheoldred Full Art NM MH2",        "is_full_art",    True),
    ("Sheoldred Promo Pack NM MH2",      "promo_types",    ["promopack"]),
    ("Sheoldred Prerelease NM MH2",      "promo_types",    ["prerelease"]),
    ("Sheoldred Buy a Box NM MH2",       "promo_types",    ["buyabox"]),
    ("Sheoldred NM MH2 MTG",            "frame_effects",  []),  # no signals
    ("Sheoldred Retro Old Border NM MH2", "frame_effects", ["retro"]),  # dedup: two synonyms → one entry
])
def test_parse_frame_variant(title, expected_key, expected_val):
    result = parse_frame_variant(title)
    assert result[expected_key] == expected_val


# --- conflicts_with_expected ---

def test_no_conflict_when_title_has_no_frame_signal():
    """Permissive: title without frame signal never conflicts."""
    parsed = {"frame_effects": [], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": ["showcase"], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is False


def test_conflict_when_title_showcase_but_card_is_regular():
    parsed = {"frame_effects": ["showcase"], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": [], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is True


def test_conflict_when_title_borderless_but_card_is_not():
    parsed = {"frame_effects": [], "is_borderless": True, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": [], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is True


def test_no_conflict_when_both_showcase():
    parsed = {"frame_effects": ["showcase"], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": ["showcase"], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is False


def test_no_conflict_when_card_regular_title_has_no_signal():
    parsed = {"frame_effects": [], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": [], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is False
