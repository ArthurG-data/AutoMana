"""Unit tests for the pure PriceCharting matching helpers."""
import pytest

from automana.core.services.app_integration.pricecharting import pc_matching as m


# ── normalize_set_name ───────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("The Brothers' War", "brothers war"),
    ("Tenth Edition", "10th edition"),
    ("Limited Edition Alpha", "alpha"),
    ("Classic Sixth Edition", "6th edition"),
    ("M10", "magic 2010"),
    ("M14", "magic 2014"),
    ("Ravnica: City of Guilds", "ravnica city of guilds"),
])
def test_normalize_set_name(raw, expected):
    assert m.normalize_set_name(raw) == expected


# ── match_set_code (4-pass + override) ───────────────────────────────────────
@pytest.fixture
def index():
    return m.build_set_code_index([
        {"set_name": "Modern Horizons 2", "set_code": "MH2"},
        {"set_name": "Forgotten Realms Commander", "set_code": "AFC"},
        {"set_name": "Magic 2014 Core Set", "set_code": "M14"},
        {"set_name": "Revised Edition", "set_code": "3ED"},
        {"set_name": "Dominaria United", "set_code": "DMU"},
        {"set_name": "Duel Decks: Elves vs. Goblins", "set_code": "dd1"},
        {"set_name": "Duel Decks Anthology: Elves vs. Goblins", "set_code": "evg"},
        {"set_name": "The List", "set_code": "plst"},
    ])


def test_match_duel_deck(index):
    assert m.match_set_code("magic elves vs goblins", index) == ("dd1", "duel_deck")


def test_match_duel_deck_anthology(index):
    assert m.match_set_code("magic anthology elves vs goblins", index) == ("evg", "duel_deck")


def test_match_the_list_override(index):
    # "the list reprints" -> plst override (PC's flat-numbered List set)
    assert m.match_set_code("magic the list reprints", index) == ("plst", "override")


def test_match_exact(index):
    assert m.match_set_code("magic modern horizons 2", index) == ("MH2", "exact")


def test_match_override(index):
    # "beta" -> override leb, regardless of index contents
    assert m.match_set_code("Beta", index) == ("leb", "override")


def test_match_suffix(index):
    # DB "forgotten realms commander" (3 words) is a suffix of the PC name
    code, method = m.match_set_code(
        "Adventures in the Forgotten Realms Commander", index
    )
    assert (code, method) == ("AFC", "suffix")


def test_match_prefix(index):
    # "revised" is a >=6-char prefix of "revised edition"
    assert m.match_set_code("Revised", index) == ("3ED", "prefix")


def test_match_fuzzy(index):
    code, method = m.match_set_code("Dominara United", index)  # typo
    assert (code, method) == ("DMU", "fuzzy")


def test_match_none(index):
    assert m.match_set_code("1999 World Championship", index) == (None, None)


# ── parse_finish ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("title,fid", [
    ("Ragavan [Etched Foil] #11", 3),
    ("Ragavan [Foil] #138", 2),
    ("Sheoldred [Prerelease] #107", 2),
    ("Ragavan #138", 1),
    ("Some Card [Showcase] #5", 1),
    ("Foil Promo Without Bracket", 2),   # foil word anywhere in title
])
def test_parse_finish(title, fid):
    assert m.parse_finish(title) == fid


# ── clean_card_name / extract_bracket_tag ────────────────────────────────────
def test_clean_card_name():
    assert m.clean_card_name("Ragavan, Nimble Pilferer [Foil] #138") == "Ragavan, Nimble Pilferer"
    assert m.clean_card_name("Black Lotus") == "Black Lotus"


def test_extract_bracket_tag():
    assert m.extract_bracket_tag("Card [Showcase Foil] #5") == "Showcase Foil"
    assert m.extract_bracket_tag("Card #5") == ""


# ── score_candidate ──────────────────────────────────────────────────────────
def test_score_rewards_present_treatment():
    row = {"frame_effects": ["showcase"], "border_color_name": "black", "full_art": False}
    assert m.score_candidate(row, "showcase") == 3


def test_score_penalises_absent_treatment():
    row = {"frame_effects": [], "border_color_name": "black", "full_art": False}
    assert m.score_candidate(row, "showcase") == -2


def test_score_borderless_uses_border_color():
    row = {"frame_effects": [], "border_color_name": "borderless", "full_art": False}
    assert m.score_candidate(row, "borderless") == 3


def test_score_fullart_uses_full_art_flag():
    row = {"frame_effects": [], "border_color_name": "black", "full_art": True}
    assert m.score_candidate(row, "full art") == 3


# ── resolve_card_match (tiebreakers) ─────────────────────────────────────────
def test_resolve_empty_returns_none():
    assert m.resolve_card_match([], "Card #1", None) is None


def test_resolve_single_candidate():
    cands = [{"card_version_id": "cv1", "card_name": "Card", "collector_number": "1"}]
    out = m.resolve_card_match(cands, "Card [Foil] #1", None)
    assert out["card_version_id"] == "cv1"
    assert out["finish_id"] == 2


def test_resolve_treatment_tiebreak():
    cands = [
        {"card_version_id": "plain", "frame_effects": [], "border_color_name": "black", "collector_number": "10"},
        {"card_version_id": "showcase", "frame_effects": ["showcase"], "border_color_name": "black", "collector_number": "300"},
    ]
    out = m.resolve_card_match(cands, "Card [Showcase] #300", None)
    assert out["card_version_id"] == "showcase"


def test_resolve_tcgplayer_tiebreak():
    # Same treatment score (none) -> tcgplayer id disambiguates foil vs non-foil
    cands = [
        {"card_version_id": "nonfoil", "frame_effects": [], "border_color_name": "black",
         "collector_number": "138", "tcgplayer_id": "239857"},
        {"card_version_id": "foil", "frame_effects": [], "border_color_name": "black",
         "collector_number": "138", "tcgplayer_id": "999999"},
    ]
    out = m.resolve_card_match(cands, "Ragavan #138", "239857")
    assert out["card_version_id"] == "nonfoil"


@pytest.mark.parametrize("title,expected", [
    ("Craw Wurm #191", "191"),
    ("Ragavan [Extended Art] #315", "315"),
    ("Card #291a", "291a"),
    ("Sealed Booster Box", None),
])
def test_extract_collector_number(title, expected):
    assert m.extract_collector_number(title) == expected


def test_resolve_collector_filter_selects_printing():
    # #315 must win over #138 even when no treatment/tcg signal distinguishes —
    # the collector token in the title pins the printing (Pass 1). Regression:
    # without the filter this fell through to lowest-collector and picked #138.
    cands = [
        {"card_version_id": "p138", "frame_effects": [], "border_color_name": "black", "collector_number": "138"},
        {"card_version_id": "p315", "frame_effects": ["inverted"], "border_color_name": "borderless", "collector_number": "315"},
    ]
    out = m.resolve_card_match(cands, "Ragavan [Extended Art] #315", None)
    assert out["card_version_id"] == "p315"
    assert out["collector_number"] == "315"


def test_resolve_collector_filter_ignored_when_no_candidate_matches():
    # Title says #999 but no candidate has it -> don't drop everything; fall back.
    cands = [
        {"card_version_id": "only", "frame_effects": [], "border_color_name": "black", "collector_number": "5"},
    ]
    out = m.resolve_card_match(cands, "Promo Card #999", None)
    assert out["card_version_id"] == "only"


def test_resolve_lowest_collector_fallback():
    cands = [
        {"card_version_id": "high", "frame_effects": [], "border_color_name": "black", "collector_number": "300"},
        {"card_version_id": "low", "frame_effects": [], "border_color_name": "black", "collector_number": "55"},
    ]
    out = m.resolve_card_match(cands, "Card #55", None)
    assert out["card_version_id"] == "low"


# ── certainty scoring ────────────────────────────────────────────────────────
def test_certainty_tcg_confirmed_is_high():
    cands = [
        {"card_version_id": "a", "frame_effects": [], "border_color_name": "black", "collector_number": "1", "tcgplayer_id": "500"},
        {"card_version_id": "b", "frame_effects": [], "border_color_name": "black", "collector_number": "1", "tcgplayer_id": "600"},
    ]
    out = m.resolve_card_match(cands, "Card #1", "500", tcg_votes=30)
    assert out["card_version_id"] == "a"
    assert out["match_method"] == "tcg"
    assert out["certainty"] >= 95


def test_certainty_unique_name():
    cands = [{"card_version_id": "a", "collector_number": "1"}]
    out = m.resolve_card_match(cands, "Card #1", None)
    assert out["match_method"] == "name"
    assert out["certainty"] == 80


def test_certainty_ambiguous_fallback_is_low():
    cands = [
        {"card_version_id": "a", "frame_effects": [], "border_color_name": "black", "collector_number": "5"},
        {"card_version_id": "b", "frame_effects": [], "border_color_name": "black", "collector_number": "9"},
    ]
    out = m.resolve_card_match(cands, "Card with no number", None)
    assert out["match_method"] == "ambiguous"
    assert out["certainty"] == 40


def test_certainty_penalised_for_fuzzy_set():
    cands = [{"card_version_id": "a", "collector_number": "1"}]
    out = m.resolve_card_match(cands, "Card #1", None, set_method="fuzzy")
    assert out["certainty"] == 60   # 80 name - 20 fuzzy-set penalty
