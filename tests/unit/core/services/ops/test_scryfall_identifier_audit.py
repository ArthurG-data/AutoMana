"""Tests for ops.audit.scryfall_identifier_coverage.

Two stubbed dependencies:
  - file scanner (`_scan_fn` injection seam) — feeds source-side counts
  - card_repository — feeds db-side counts via two repo methods

The service then merges them into the standard report envelope.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.services.ops.scryfall_identifier_audit import (
    _classify,
    _severity_from_gap,
    scryfall_identifier_coverage,
)

pytestmark = pytest.mark.unit


# ---------- pure helper tests ----------

@pytest.mark.parametrize("refs,distinct,expected", [
    (100, 100, "per-printing"),
    (100, 99, "per-printing"),                # ratio 1.01
    (113695, 37236, "per-abstract-card"),     # real oracle_id ratio
    (100, 75, "per-printing-with-collisions"),  # ratio 1.33
    (0, 0, "no-data"),
])
def test_classify_uses_refs_per_distinct_ratio(refs, distinct, expected):
    assert _classify(refs, distinct) == expected


@pytest.mark.parametrize("gap,expected", [
    (0.0, "ok"),
    (0.5, "ok"),
    (1.0, "warn"),
    (4.99, "warn"),
    (5.0, "error"),
    (None, "warn"),
])
def test_severity_from_gap_uses_expected_thresholds(gap, expected):
    assert _severity_from_gap(gap, "per-printing") == expected


# ---------- end-to-end service test ----------

def _scan_stub_full(path):
    """Inline scan result modeled on a tiny synthetic 100-card file.

    Includes identifier value distributions chosen so each classification
    branch fires:
      - scryfall_id        100/100 distinct → per-printing
      - oracle_id          100 refs / 33 distinct → per-abstract-card
      - tcgplayer_id        90 refs / 88 distinct → per-printing
      - tcgplayer_etched_id  3 refs /  3 distinct → per-printing
      - cardmarket_id       85 refs / 85 distinct → per-printing
      - multiverse_id       60 refs / 60 distinct → per-printing
    """
    return {
        "scryfall_id":         {"presence": 100, "distinct": 100, "refs": 100},
        "oracle_id":           {"presence": 100, "distinct": 33,  "refs": 100},
        "tcgplayer_id":        {"presence": 90,  "distinct": 88,  "refs": 90},
        "tcgplayer_etched_id": {"presence": 3,   "distinct": 3,   "refs": 3},
        "cardmarket_id":       {"presence": 85,  "distinct": 85,  "refs": 85},
        "multiverse_id":       {"presence": 60,  "distinct": 60,  "refs": 60},
        "__total__":           {"cards": 100},
    }


def _make_repo(*, total_card_versions=100, total_unique_cards=33,
               db_audit_rows=None):
    """Build a CardReferenceRepository mock with sane defaults matching
    the synthetic 100-card scan above."""
    if db_audit_rows is None:
        db_audit_rows = [
            {"identifier_name": "scryfall_id",         "total_rows": 100, "distinct_values": 100, "distinct_card_versions": 100, "distinct_unique_cards": 33},
            {"identifier_name": "oracle_id",           "total_rows": 33,  "distinct_values": 33,  "distinct_card_versions": 33,  "distinct_unique_cards": 33},
            {"identifier_name": "tcgplayer_id",        "total_rows": 88,  "distinct_values": 88,  "distinct_card_versions": 88,  "distinct_unique_cards": 30},
            {"identifier_name": "tcgplayer_etched_id", "total_rows": 3,   "distinct_values": 3,   "distinct_card_versions": 3,   "distinct_unique_cards": 3},
            {"identifier_name": "cardmarket_id",       "total_rows": 85,  "distinct_values": 85,  "distinct_card_versions": 85,  "distinct_unique_cards": 28},
            {"identifier_name": "multiverse_id",       "total_rows": 60,  "distinct_values": 60,  "distinct_card_versions": 60,  "distinct_unique_cards": 20},
        ]
    repo = AsyncMock()
    repo.fetch_identifier_audit_counts.return_value = db_audit_rows
    repo.fetch_card_universe_counts.return_value = {
        "total_card_versions": total_card_versions,
        "total_unique_cards": total_unique_cards,
    }
    return repo


@pytest.mark.asyncio
async def test_audit_returns_standard_envelope_with_one_row_per_identifier():
    repo = _make_repo()
    out = await scryfall_identifier_coverage(
        card_repository=repo,
        raw_file_path="/fake/path.json",
        _scan_fn=_scan_stub_full,
    )
    assert out["check_set"] == "scryfall_identifier_coverage_audit"
    assert out["total_checks"] == 6  # 5 top-level + 1 list-field
    paths = {r["check_name"] for r in out["rows"]}
    assert paths == {
        "card_catalog.identifier_audit.scryfall_id",
        "card_catalog.identifier_audit.oracle_id",
        "card_catalog.identifier_audit.tcgplayer_id",
        "card_catalog.identifier_audit.tcgplayer_etched_id",
        "card_catalog.identifier_audit.cardmarket_id",
        "card_catalog.identifier_audit.multiverse_id",
    }
    assert out["raw_file"] == "/fake/path.json"
    assert out["total_cards_in_file"] == 100
    assert out["total_card_versions_in_db"] == 100
    assert out["total_unique_cards_in_db"] == 33


@pytest.mark.asyncio
async def test_audit_oracle_id_uses_unique_cards_denominator():
    """oracle_id is per-abstract-card → denominator must be unique_cards_ref,
    not card_version. Without that, stored_pct would be 33% (a false alarm)."""
    repo = _make_repo()
    out = await scryfall_identifier_coverage(
        card_repository=repo,
        raw_file_path="/fake/path.json",
        _scan_fn=_scan_stub_full,
    )
    oracle = next(r for r in out["rows"] if r["details"]["identifier_name"] == "oracle_id")
    assert oracle["details"]["classification"] == "per-abstract-card"
    assert oracle["details"]["db_denominator"] == "unique_cards_ref"
    assert oracle["details"]["db_denominator_count"] == 33
    assert oracle["row_count"] == 100.0  # 33/33 stored = 100%
    assert oracle["severity"] == "ok"


@pytest.mark.asyncio
async def test_audit_per_printing_identifier_uses_card_version_denominator():
    repo = _make_repo()
    out = await scryfall_identifier_coverage(
        card_repository=repo, raw_file_path="/fake/path.json", _scan_fn=_scan_stub_full,
    )
    scryfall = next(r for r in out["rows"] if r["details"]["identifier_name"] == "scryfall_id")
    assert scryfall["details"]["classification"] == "per-printing"
    assert scryfall["details"]["db_denominator"] == "card_version"
    assert scryfall["details"]["db_denominator_count"] == 100
    assert scryfall["row_count"] == 100.0
    assert scryfall["severity"] == "ok"


@pytest.mark.asyncio
async def test_audit_flags_significant_etl_drop_as_error():
    """Source has 100 scryfall_id but DB only has 80 → 20% gap → ERROR."""
    repo = _make_repo(db_audit_rows=[
        {"identifier_name": "scryfall_id",         "total_rows": 80, "distinct_values": 80, "distinct_card_versions": 80, "distinct_unique_cards": 28},
        {"identifier_name": "oracle_id",           "total_rows": 33, "distinct_values": 33, "distinct_card_versions": 33, "distinct_unique_cards": 33},
        {"identifier_name": "tcgplayer_id",        "total_rows": 88, "distinct_values": 88, "distinct_card_versions": 88, "distinct_unique_cards": 30},
        {"identifier_name": "tcgplayer_etched_id", "total_rows": 3,  "distinct_values": 3,  "distinct_card_versions": 3,  "distinct_unique_cards": 3},
        {"identifier_name": "cardmarket_id",       "total_rows": 85, "distinct_values": 85, "distinct_card_versions": 85, "distinct_unique_cards": 28},
        {"identifier_name": "multiverse_id",       "total_rows": 60, "distinct_values": 60, "distinct_card_versions": 60, "distinct_unique_cards": 20},
    ])
    out = await scryfall_identifier_coverage(
        card_repository=repo, raw_file_path="/fake/path.json", _scan_fn=_scan_stub_full,
    )
    scryfall = next(r for r in out["rows"] if r["details"]["identifier_name"] == "scryfall_id")
    assert scryfall["details"]["gap_pct"] == 20.0
    assert scryfall["severity"] == "error"


@pytest.mark.asyncio
async def test_audit_returns_error_envelope_when_no_raw_file_found(monkeypatch):
    """No raw_file_path provided AND no file in the default directory → graceful error row."""
    monkeypatch.setattr(
        "automana.core.services.ops.scryfall_identifier_audit._newest_raw_file",
        lambda *a, **kw: None,
    )
    repo = _make_repo()
    out = await scryfall_identifier_coverage(card_repository=repo)
    assert out["error_count"] == 1
    assert "no Scryfall raw file found" in out["rows"][0]["details"]["exception"]


def test_scan_raw_file_streams_real_json(tmp_path):
    """End-to-end check that the scanner actually walks an ijson stream
    against a real on-disk file. Uses a tiny synthetic 3-card array."""
    import json
    from automana.core.services.ops.scryfall_identifier_audit import _scan_raw_file

    sample = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "oracle_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "tcgplayer_id": 1,
            "cardmarket_id": 11,
            "multiverse_ids": [101],
        },
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "oracle_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",  # reprint, same oracle_id
            "tcgplayer_id": 2,
            "cardmarket_id": 12,
            "multiverse_ids": [102, 103],  # multiple multiverse ids
        },
        {
            "id": "00000000-0000-0000-0000-000000000003",
            "oracle_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            # no tcgplayer_id, no cardmarket_id, no multiverse_ids
        },
    ]
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(sample))

    scan = _scan_raw_file(str(path))
    assert scan["__total__"]["cards"] == 3
    assert scan["scryfall_id"] == {"presence": 3, "distinct": 3, "refs": 3}
    assert scan["oracle_id"] == {"presence": 3, "distinct": 2, "refs": 3}  # 2 reprints share
    assert scan["tcgplayer_id"] == {"presence": 2, "distinct": 2, "refs": 2}
    assert scan["cardmarket_id"] == {"presence": 2, "distinct": 2, "refs": 2}
    assert scan["multiverse_id"] == {"presence": 2, "distinct": 3, "refs": 3}  # card2 has 2 ids
