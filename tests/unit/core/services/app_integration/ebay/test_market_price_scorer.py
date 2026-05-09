from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)


# ── build_query_string ──────────────────────────────────────────────────────

def test_query_includes_card_name_words():
    q = build_query_string("Sheoldred, the Apocalypse", None, None, None)
    assert "Sheoldred" in q
    assert "Apocalypse" in q

def test_query_strips_punctuation_from_card_name():
    q = build_query_string("Sheoldred, the Apocalypse", None, None, None)
    assert "," not in q

def test_query_appends_set_code():
    q = build_query_string("Lightning Bolt", "M10", None, None)
    assert "M10" in q

def test_query_appends_foil():
    q = build_query_string("Mox Pearl", None, True, None)
    assert "foil" in q.lower()

def test_query_appends_nonfoil():
    q = build_query_string("Mox Pearl", None, False, None)
    assert "non-foil" in q.lower()

def test_query_appends_frame():
    q = build_query_string("Sheoldred, the Apocalypse", "DMR", None, "showcase")
    assert "showcase" in q.lower()

def test_query_ends_with_mtg():
    q = build_query_string("Sheoldred, the Apocalypse", None, None, None)
    assert q.strip().upper().endswith("MTG")


# ── score_title ─────────────────────────────────────────────────────────────

def test_exact_card_name_match_contributes_half():
    score = score_title("Sheoldred the Apocalypse NM MTG", "Sheoldred the Apocalypse", None, None, None)
    assert score >= 0.5

def test_reject_keyword_gives_zero():
    score = score_title("Sheoldred Apocalypse proxy MTG", "Sheoldred Apocalypse", None, None, None)
    assert score == 0.0

def test_reject_keyword_psa_gives_zero():
    score = score_title("Sheoldred Apocalypse PSA 10 MTG", "Sheoldred Apocalypse", None, None, None)
    assert score == 0.0

def test_set_code_bonus():
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    with_set = score_title("Sheoldred Apocalypse DMR MTG", "Sheoldred Apocalypse", "DMR", None, None)
    assert with_set > base

def test_foil_match_bonus():
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    with_foil = score_title("Sheoldred Apocalypse foil MTG", "Sheoldred Apocalypse", None, True, None)
    assert with_foil > base

def test_foil_mismatch_no_bonus():
    # requesting foil, title says non-foil → no foil bonus
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    mismatch = score_title("Sheoldred Apocalypse non-foil MTG", "Sheoldred Apocalypse", None, True, None)
    assert mismatch <= base

def test_frame_match_bonus():
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    with_frame = score_title("Sheoldred Apocalypse showcase MTG", "Sheoldred Apocalypse", None, None, "showcase")
    assert with_frame > base

def test_score_capped_at_one():
    score = score_title("Sheoldred Apocalypse DMR foil showcase MTG", "Sheoldred Apocalypse", "DMR", True, "showcase")
    assert 0.0 <= score <= 1.0


def test_lot_in_name_not_rejected():
    # "lot" is a reject keyword but "Lotus" should NOT be rejected
    score = score_title("Black Lotus LEA MTG", "Black Lotus", "LEA", None, None)
    assert score > 0.0

def test_alternate_art_not_rejected():
    # "alter" is a reject keyword but "alternate" should NOT be rejected
    score = score_title("Sheoldred Apocalypse DMR alternate art MTG", "Sheoldred Apocalypse", "DMR", None, None)
    assert score > 0.0

def test_possessive_card_name_matches():
    # apostrophe in card name should not block matching
    score = score_title("Urza's Saga MH2 MTG", "Urza's Saga", "MH2", None, None)
    assert score >= 0.5

def test_extended_art_frame_matches():
    # "extended_art" frame should match "extended art" in title
    score_with = score_title("Sheoldred Apocalypse extended art MTG", "Sheoldred Apocalypse", None, None, "extended_art")
    score_without = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    assert score_with > score_without

def test_nonfoil_no_hyphen_not_treated_as_foil():
    # "nonfoil" without hyphen should NOT get foil bonus when is_foil=True
    score_nonfoil = score_title("Sheoldred Apocalypse nonfoil MTG", "Sheoldred Apocalypse", None, True, None)
    score_base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    assert score_nonfoil <= score_base
