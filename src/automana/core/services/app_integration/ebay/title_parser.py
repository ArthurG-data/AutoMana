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
    ("etched",       "ETCHED"),    # bare "etched" without "foil" word
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


_FRAME_EFFECT_PATTERNS: list[tuple[str, str]] = [
    ("extended art", "extendedart"),
    ("ext art",      "extendedart"),
    (r"\bea\b",      "extendedart"),   # word-boundary match
    ("showcase",     "showcase"),
    ("retro",        "retro"),
    ("old border",   "retro"),
    ("old frame",    "retro"),
    ("anime",        "inverted"),
]

_PROMO_PATTERNS: list[tuple[str, str]] = [
    ("promo pack",   "promopack"),
    ("prerelease",   "prerelease"),
    ("pre-release",  "prerelease"),
    ("buy a box",    "buyabox"),
    ("buyabox",      "buyabox"),
    (r"\bbab\b",     "buyabox"),
    ("judge",        "judgegift"),
    ("date stamp",   "datestamped"),
]

_BORDERLESS_RE = re.compile(r"\bborderless\b", re.IGNORECASE)
_FULL_ART_RE   = re.compile(r"\bfull[-\s]?art\b", re.IGNORECASE)


def parse_frame_variant(title: str) -> dict:
    """Detect treatment signals from an eBay listing title.

    Returns a dict with keys: frame_effects (list[str]), is_borderless (bool),
    is_full_art (bool), promo_types (list[str]).
    """
    lower = title.lower()
    frame_effects: list[str] = []
    promo_types: list[str] = []

    for pattern, effect in _FRAME_EFFECT_PATTERNS:
        if pattern.startswith(r"\b"):
            if re.search(pattern, lower):
                frame_effects.append(effect)
        elif pattern in lower:
            frame_effects.append(effect)

    for pattern, ptype in _PROMO_PATTERNS:
        if pattern.startswith(r"\b"):
            if re.search(pattern, lower):
                promo_types.append(ptype)
        elif pattern in lower:
            promo_types.append(ptype)

    return {
        "frame_effects": frame_effects,
        "is_borderless": bool(_BORDERLESS_RE.search(title)),
        "is_full_art":   bool(_FULL_ART_RE.search(title)),
        "promo_types":   promo_types,
    }


def conflicts_with_expected(parsed: dict, card: dict) -> bool:
    """Return True only on hard conflicts between parsed title signals and card attributes.

    Permissive by design: a title with no frame signal never conflicts regardless of
    what the card's frame_effects are — many sellers don't mention treatment explicitly.
    """
    card_frame_effects: list[str] = card.get("frame_effects") or []
    card_borderless: bool = (card.get("border_color_name") or "").lower() == "borderless"
    card_full_art: bool = bool(card.get("full_art"))

    parsed_frames: list[str] = parsed.get("frame_effects") or []
    parsed_borderless: bool = parsed.get("is_borderless", False)
    parsed_full_art: bool = parsed.get("is_full_art", False)

    # Title asserts a frame effect the card doesn't have → conflict.
    for effect in parsed_frames:
        if effect not in card_frame_effects:
            return True

    # Title asserts borderless but card is not borderless → conflict.
    if parsed_borderless and not card_borderless:
        return True

    # Title asserts full art but card is not full art → conflict.
    if parsed_full_art and not card_full_art:
        return True

    return False
