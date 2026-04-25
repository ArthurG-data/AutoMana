"""
Tests for src/automana/core/services/analytics/utils.py

Pure-logic module — no mocks required. Synchronous.
Coverage target: >= 90% line + branch.

Functions under test:
  - parse_title_for_condition(title: str) -> str
  - parsed_description_for_condition(description: str) -> str
  - create_condition_pattern_map() -> Dict[str, str]  (indirectly via the above)

Strategy:
  parse_title_for_condition has four detection layers:
    1. Pattern map built from condition_variations (main path)
    2. Fallback abbreviation map (single-letter / short codes)
    3. Inference patterns (keyword-based)
    4. Return "Unknown"

  parsed_description_for_condition shares layers 1 and 4 only.

  Use @pytest.mark.parametrize to cover all meaningful branches efficiently.
  Avoid testing the same pattern twice — one representative per condition
  per layer is sufficient.
"""
import pytest

pytestmark = pytest.mark.unit

from automana.core.services.analytics.utils import (
    create_condition_pattern_map,
    parse_title_for_condition,
    parsed_description_for_condition,
)


# ---------------------------------------------------------------------------
# create_condition_pattern_map
# ---------------------------------------------------------------------------

class TestCreateConditionPatternMap:
    def test_returns_non_empty_dict(self):
        pattern_map = create_condition_pattern_map()
        assert isinstance(pattern_map, dict)
        assert len(pattern_map) > 0

    def test_all_values_are_known_condition_names(self):
        expected_conditions = {
            "Near Mint", "Lightly Played", "Moderately Played",
            "Heavily Played", "Damaged", "Graded", "Sealed",
        }
        pattern_map = create_condition_pattern_map()
        assert set(pattern_map.values()).issubset(expected_conditions)

    def test_all_keys_are_valid_regex_strings(self):
        import re
        pattern_map = create_condition_pattern_map()
        for pattern in pattern_map.keys():
            # Should not raise
            re.compile(pattern)


# ---------------------------------------------------------------------------
# parse_title_for_condition — main pattern map path
# ---------------------------------------------------------------------------

class TestParseTitleForConditionPatternMap:
    @pytest.mark.parametrize("title,expected", [
        # Exact standard names
        ("Near Mint",           "Near Mint"),
        ("Lightly Played",      "Lightly Played"),
        ("Moderately Played",   "Moderately Played"),
        ("Heavily Played",      "Heavily Played"),
        ("Damaged",             "Damaged"),
        ("Graded",              "Graded"),
        ("Sealed",              "Sealed"),
        # Common abbreviations defined in condition_variations
        ("NM foil",             "Near Mint"),
        ("LP",                  "Lightly Played"),
        ("MP",                  "Moderately Played"),
        ("HP card",             "Heavily Played"),
        ("DMG",                 "Damaged"),
        ("PSA 10",              "Graded"),
        ("factory sealed",      "Sealed"),
        # Case insensitivity
        ("near mint",           "Near Mint"),
        ("LIGHTLY PLAYED",      "Lightly Played"),
        ("mod played",          "Moderately Played"),
        # Mint is a Near Mint alias in condition_variations
        ("Mint condition",      "Near Mint"),
        # Slight variations listed in condition_variations
        ("slightly played",     "Lightly Played"),
        ("heavily play",        "Heavily Played"),
        ("badly damaged",       "Damaged"),
        ("factory sealed",      "Sealed"),
        ("beckett graded",      "Graded"),
    ])
    def test_pattern_map_matches(self, title, expected):
        assert parse_title_for_condition(title) == expected


# ---------------------------------------------------------------------------
# parse_title_for_condition — None / empty guard
# ---------------------------------------------------------------------------

class TestParseTitleForConditionGuards:
    def test_none_input_returns_unknown(self):
        assert parse_title_for_condition(None) == "Unknown"

    def test_empty_string_returns_unknown(self):
        assert parse_title_for_condition("") == "Unknown"

    def test_whitespace_only_returns_unknown(self):
        # strips to empty, nothing matches
        assert parse_title_for_condition("   ") == "Unknown"


# ---------------------------------------------------------------------------
# parse_title_for_condition — inference layer
# These hit the third detection layer (keywords not in condition_variations)
# ---------------------------------------------------------------------------

class TestParseTitleForConditionInference:
    @pytest.mark.parametrize("title,expected", [
        ("beat up old card",          "Heavily Played"),
        ("rough looking card",        "Heavily Played"),
        ("torn at the corner",        "Damaged"),
        ("ripped edge foil",          "Damaged"),
        ("big crease in it",          "Damaged"),
        ("good condition card",       "Lightly Played"),
        ("excellent card condition",  "Near Mint"),
    ])
    def test_inference_patterns(self, title, expected):
        assert parse_title_for_condition(title) == expected


# ---------------------------------------------------------------------------
# parse_title_for_condition — full unknown fallback
# ---------------------------------------------------------------------------

class TestParseTitleForConditionUnknown:
    @pytest.mark.parametrize("title", [
        "random text with no condition info",
        "foil rainbow card",
        "1234567890",
        "Alpha edition vintage",
    ])
    def test_no_match_returns_unknown(self, title):
        assert parse_title_for_condition(title) == "Unknown"


# ---------------------------------------------------------------------------
# parsed_description_for_condition
# Shares pattern-map layer 1 and the None/empty guard with parse_title.
# Does NOT have an inference layer — just assert the key shared branches.
# ---------------------------------------------------------------------------

class TestParsedDescriptionForCondition:
    def test_none_returns_unknown(self):
        assert parsed_description_for_condition(None) == "Unknown"

    def test_empty_string_returns_unknown(self):
        assert parsed_description_for_condition("") == "Unknown"

    @pytest.mark.parametrize("desc,expected", [
        ("Near Mint",     "Near Mint"),
        ("LP",            "Lightly Played"),
        ("heavily played","Heavily Played"),
        ("Damaged",       "Damaged"),
        ("PSA graded",    "Graded"),
        ("sealed box",    "Sealed"),
    ])
    def test_pattern_map_matches(self, desc, expected):
        assert parsed_description_for_condition(desc) == expected

    def test_no_match_returns_unknown(self):
        assert parsed_description_for_condition("no condition info here") == "Unknown"
