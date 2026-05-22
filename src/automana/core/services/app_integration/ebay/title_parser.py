"""Parse eBay listing titles into finish/condition/frame structured data."""
from __future__ import annotations

import re
from typing import Optional

# Maps finish code → finish_id (matches seed order in 02_card_schema.sql).
FINISH_ID_MAP: dict[str, int] = {
    "NONFOIL": 1,
    "FOIL": 2,
    "ETCHED": 3,
    "SURGE_FOIL": 4,
    "RIPPLE_FOIL": 5,
    "RAINBOW_FOIL": 6,
}

# Maps condition code → condition_id (matches seed order in 06_prices.sql).
CONDITION_ID_MAP: dict[str, int] = {
    "NM": 1,
    "LP": 2,
    "MP": 3,
    "HP": 4,
    "DMG": 5,
    "SP": 6,
}

# Ordered: most specific pattern first to avoid partial matches.
_FINISH_PATTERNS: list[tuple[str, str]] = [
    ("surge foil",   "SURGE_FOIL"),
    ("ripple foil",  "RIPPLE_FOIL"),
    ("rainbow foil", "RAINBOW_FOIL"),
    ("etched foil",  "ETCHED"),
    ("foil etched",  "ETCHED"),
]

_FOIL_RE = re.compile(r"\bfoil\b", re.IGNORECASE)
_NONFOIL_RE = re.compile(r"\bnon[-\s]?foil\b|nonfoil", re.IGNORECASE)

_EBAY_CONDITION_MAP: dict[str, str] = {
    "near mint or better": "NM",
    "near mint":           "NM",
    "lightly played":      "LP",
    "excellent":           "LP",
    "slightly played":     "SP",
    "moderately played":   "MP",
    "very good":           "MP",
    "heavily played":      "HP",
    "good":                "HP",
    "damaged":             "DMG",
    "poor":                "DMG",
    "acceptable":          "HP",
}

_TITLE_CONDITION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(nm/m|m/nm|nm\+|nm)\b", re.IGNORECASE),    "NM"),
    (re.compile(r"\b(lp|ex)\b", re.IGNORECASE),                 "LP"),
    (re.compile(r"\bsp\b", re.IGNORECASE),                      "SP"),
    (re.compile(r"\b(mp|vg)\b", re.IGNORECASE),                 "MP"),
    (re.compile(r"\b(hp|g)\b", re.IGNORECASE),                  "HP"),
    (re.compile(r"\bpld\b", re.IGNORECASE),                     "HP"),
    (re.compile(r"\b(dmg|damaged)\b", re.IGNORECASE),           "DMG"),
    (re.compile(r"\bplayed\b", re.IGNORECASE),                   "MP"),
]


def parse_finish_code(title: str) -> str:
    """Return a finish code (e.g. 'FOIL', 'ETCHED') from an eBay listing title."""
    lower = title.lower()
    for pattern, code in _FINISH_PATTERNS:
        if pattern in lower:
            return code
    if _FOIL_RE.search(title) and not _NONFOIL_RE.search(title):
        return "FOIL"
    return "NONFOIL"


def parse_condition_code(
    ebay_condition: Optional[str],
    title: str,
) -> str:
    """Return a condition code (e.g. 'NM', 'LP'). Defaults to 'NM' when ambiguous."""
    if ebay_condition:
        code = _EBAY_CONDITION_MAP.get(ebay_condition.strip().lower())
        if code:
            return code
    for pattern, code in _TITLE_CONDITION_PATTERNS:
        if pattern.search(title):
            return code
    return "NM"
