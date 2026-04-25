"""ops.audit.scryfall_identifier_coverage — on-demand source-vs-db audit.

Compares a Scryfall raw bulk JSON file against the live ``card_external_identifier``
table to produce a per-identifier breakdown:

  - source presence (how many cards in the file have the identifier)
  - source distinct values (collisions = same value used by multiple printings)
  - DB stored count and distinct values
  - classification: ``per-printing`` (refs/distinct ≈ 1) vs ``per-abstract-card``
    (ratio significantly > 1, like oracle_id at ~3x)
  - source-vs-db gap

This was the analysis that surfaced the oracle_id metric-design bug — it's now
a registered service so any future identifier shape question can be answered on
demand without ad-hoc scripts.

Severity is set per-row from the source-vs-db gap so an operator running the
audit sees red rows where the ETL is genuinely dropping data.
"""
from __future__ import annotations

import glob
import logging
import os
from typing import Any, Callable

import ijson

from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops.integrity_checks import _build_report

logger = logging.getLogger(__name__)


# Identifiers we know how to extract from a Scryfall card object. Each maps the
# identifier_name in card_identifier_ref to the Scryfall payload accessor —
# either a top-level key (``oracle_id``, ``id``, ``tcgplayer_id``, …) or a list
# field (``multiverse_ids``). `id` is Scryfall's unique-per-printing UUID, which
# the ETL stores under the ``scryfall_id`` identifier_name.
_TOP_LEVEL: dict[str, str] = {
    "scryfall_id":         "id",
    "oracle_id":           "oracle_id",
    "tcgplayer_id":        "tcgplayer_id",
    "tcgplayer_etched_id": "tcgplayer_etched_id",
    "cardmarket_id":       "cardmarket_id",
}
_LIST_FIELDS: dict[str, str] = {
    "multiverse_id": "multiverse_ids",
}

# Default location of Scryfall raw bulk dumps. The pipeline writes here.
_DEFAULT_RAW_DIR = "/data/automana_data/scryfall/raw_files"
_RAW_GLOB = "*default-cards-*.json"


def _newest_raw_file(directory: str = _DEFAULT_RAW_DIR) -> str | None:
    matches = glob.glob(os.path.join(directory, _RAW_GLOB))
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def _scan_raw_file(path: str) -> dict[str, dict]:
    """Stream a Scryfall raw JSON file once and tally per-identifier source stats.

    Returns ``{identifier_name: {presence: int, distinct: int, refs: int}}`` plus
    ``__total__: {cards: int}`` under a sentinel key.
    """
    presence: dict[str, int] = {name: 0 for name in (*_TOP_LEVEL, *_LIST_FIELDS)}
    distinct: dict[str, set] = {name: set() for name in (*_TOP_LEVEL, *_LIST_FIELDS)}
    refs: dict[str, int] = {name: 0 for name in (*_TOP_LEVEL, *_LIST_FIELDS)}
    total_cards = 0

    with open(path, "rb") as f:
        for card in ijson.items(f, "item"):
            total_cards += 1
            for name, key in _TOP_LEVEL.items():
                v = card.get(key)
                if v is None or v == "":
                    continue
                presence[name] += 1
                refs[name] += 1
                distinct[name].add(str(v))
            for name, key in _LIST_FIELDS.items():
                vals = card.get(key) or []
                if not vals:
                    continue
                presence[name] += 1
                for v in vals:
                    refs[name] += 1
                    distinct[name].add(str(v))

    out = {
        name: {
            "presence": presence[name],
            "distinct": len(distinct[name]),
            "refs": refs[name],
        }
        for name in (*_TOP_LEVEL, *_LIST_FIELDS)
    }
    out["__total__"] = {"cards": total_cards}
    return out


def _classify(refs: int, distinct: int) -> str:
    """per-printing if refs/distinct ≈ 1, per-abstract-card if significantly higher."""
    if distinct == 0:
        return "no-data"
    ratio = refs / distinct
    if ratio < 1.10:
        return "per-printing"
    if ratio < 1.50:
        return "per-printing-with-collisions"
    return "per-abstract-card"


def _severity_from_gap(gap_pct: float | None, classification: str) -> str:
    """ERROR if the ETL has dropped >5% of source presence; WARN if >1%."""
    if gap_pct is None:
        return "warn"
    if gap_pct >= 5.0:
        return "error"
    if gap_pct >= 1.0:
        return "warn"
    return "ok"


def _build_row(
    name: str,
    src: dict | None,
    db_row: dict | None,
    universe: dict,
) -> dict:
    """Assemble one report row from source-side and db-side counts."""
    src = src or {"presence": 0, "distinct": 0, "refs": 0}
    db_row = db_row or {
        "total_rows": 0,
        "distinct_values": 0,
        "distinct_card_versions": 0,
        "distinct_unique_cards": 0,
    }
    total_cards = universe["__total__"]["cards"]

    classification = _classify(src["refs"], src["distinct"])

    # Source-side presence rate (fraction of cards in file that had the field)
    source_pct = (
        round(100.0 * src["presence"] / total_cards, 2) if total_cards else None
    )

    # DB-side coverage. For per-abstract-card identifiers, measure against
    # unique_cards_ref (matches the metric semantics fixed in T16). For
    # per-printing identifiers, measure against card_version (the natural
    # 1:1 mapping). For multi-value list fields (multiverse_id), there is no
    # well-defined "covered card_versions" — fall back to distinct_card_versions
    # / total_card_versions.
    if classification == "per-abstract-card":
        denom = universe["total_unique_cards"]
        numer = db_row["distinct_unique_cards"]
        denom_label = "unique_cards_ref"
    else:
        denom = universe["total_card_versions"]
        numer = db_row["distinct_card_versions"]
        denom_label = "card_version"

    stored_pct = round(100.0 * numer / denom, 2) if denom else None
    gap_pct = (
        round(source_pct - stored_pct, 2)
        if source_pct is not None and stored_pct is not None
        else None
    )

    return {
        "check_name": f"card_catalog.identifier_audit.{name}",
        "severity": _severity_from_gap(gap_pct, classification),
        "row_count": stored_pct,
        "details": {
            "identifier_name": name,
            "classification": classification,
            "source_presence": src["presence"],
            "source_distinct": src["distinct"],
            "source_refs": src["refs"],
            "source_refs_per_distinct": (
                round(src["refs"] / src["distinct"], 3) if src["distinct"] else None
            ),
            "source_pct": source_pct,
            "db_total_rows": db_row["total_rows"],
            "db_distinct_values": db_row["distinct_values"],
            "db_distinct_card_versions": db_row["distinct_card_versions"],
            "db_distinct_unique_cards": db_row["distinct_unique_cards"],
            "db_denominator": denom_label,
            "db_denominator_count": denom,
            "stored_pct": stored_pct,
            "gap_pct": gap_pct,
            "description": (
                f"Source-vs-DB coverage for {name}; severity from gap_pct."
            ),
            "category": "audit",
        },
    }


@ServiceRegistry.register(
    "ops.audit.scryfall_identifier_coverage",
    db_repositories=["card"],
)
async def scryfall_identifier_coverage(
    card_repository: CardReferenceRepository,
    raw_file_path: str | None = None,
    *,
    _scan_fn: Callable[[str], dict[str, dict]] | None = None,
) -> dict:
    """Compare a Scryfall raw bulk JSON file against ``card_external_identifier``.

    Args:
        raw_file_path: Path to the Scryfall raw JSON. If omitted, the newest
            ``*default-cards-*.json`` under the configured raw_files directory
            is used.
        _scan_fn: Test seam — override the file-streaming scanner.

    Returns the standard integrity-report envelope. One row per identifier
    name, severity set from the source-vs-db gap. The ``details`` dict on each
    row carries the raw counts so an operator can see exactly where any drop
    happened.
    """
    path = raw_file_path or _newest_raw_file()
    if path is None:
        return _build_report(
            "scryfall_identifier_coverage_audit",
            [{
                "check_name": "card_catalog.identifier_audit",
                "severity": "error",
                "row_count": None,
                "details": {
                    "exception": (
                        "no Scryfall raw file found — pass raw_file_path or check "
                        f"that {_DEFAULT_RAW_DIR} contains a *default-cards-*.json"
                    ),
                    "description": "audit input missing",
                    "category": "audit",
                },
            }],
        )

    logger.info("scryfall_audit_start", extra={"raw_file": path})
    scan = (_scan_fn or _scan_raw_file)(path)

    db_rows = await card_repository.fetch_identifier_audit_counts()
    universe: dict[str, Any] = {
        **(await card_repository.fetch_card_universe_counts()),
        "__total__": scan["__total__"],
    }
    db_by_name = {r["identifier_name"]: r for r in db_rows}

    rows = []
    for name in (*_TOP_LEVEL, *_LIST_FIELDS):
        rows.append(_build_row(name, scan.get(name), db_by_name.get(name), universe))

    report = _build_report("scryfall_identifier_coverage_audit", rows)
    report["raw_file"] = path
    report["total_cards_in_file"] = scan["__total__"]["cards"]
    report["total_card_versions_in_db"] = universe["total_card_versions"]
    report["total_unique_cards_in_db"] = universe["total_unique_cards"]
    return report
