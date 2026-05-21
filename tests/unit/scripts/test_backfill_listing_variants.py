"""Unit tests for pure input-parsing helpers in backfill_listing_variants."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))

from backfill_listing_variants import _parse_condition, _parse_finish


# ── _parse_condition ──────────────────────────────────────────────────────────

def test_parse_condition_empty_returns_default():
    assert _parse_condition("", "NM") == "NM"

def test_parse_condition_exact_match_case_insensitive():
    assert _parse_condition("lp", "NM") == "LP"
    assert _parse_condition("LP", "NM") == "LP"

def test_parse_condition_prefix_match():
    assert _parse_condition("m", "NM") == "MP"
    assert _parse_condition("h", "NM") == "HP"
    assert _parse_condition("d", "NM") == "DMG"
    assert _parse_condition("n", "NM") == "NM"

def test_parse_condition_invalid_returns_none():
    assert _parse_condition("xyz", "NM") is None

def test_parse_condition_ambiguous_returns_none():
    assert _parse_condition("z", "NM") is None


# ── _parse_finish ─────────────────────────────────────────────────────────────

def test_parse_finish_empty_returns_default():
    assert _parse_finish("", "NONFOIL") == "NONFOIL"

def test_parse_finish_exact_match_case_insensitive():
    assert _parse_finish("foil", "NONFOIL") == "FOIL"
    assert _parse_finish("FOIL", "NONFOIL") == "FOIL"

def test_parse_finish_prefix_nonfoil():
    assert _parse_finish("non", "NONFOIL") == "NONFOIL"
    assert _parse_finish("n", "NONFOIL") == "NONFOIL"

def test_parse_finish_prefix_foil():
    assert _parse_finish("fo", "NONFOIL") == "FOIL"

def test_parse_finish_prefix_etched():
    assert _parse_finish("e", "NONFOIL") == "ETCHED"

def test_parse_finish_f_uniquely_matches_foil():
    assert _parse_finish("f", "NONFOIL") == "FOIL"

def test_parse_finish_invalid_returns_none():
    assert _parse_finish("zzz", "NONFOIL") is None
