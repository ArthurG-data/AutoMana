# src/automana/core/services/app_integration/ebay/market_price_scorer.py
import re
from typing import Optional

_SINGLE_WORD_REJECTS: frozenset[str] = frozenset({
    "proxy", "fake", "alter", "custom", "token", "lot", "playset",
    "bundle", "signed", "psa", "bgs", "cgc", "graded",
})

_PHRASE_REJECTS: tuple[str, ...] = ("reprint lot",)

# Pre-compile word-boundary patterns for single-word rejects
_REJECT_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(r"\b" + re.escape(kw) + r"\b") for kw in _SINGLE_WORD_REJECTS
)

# Keep REJECT_KEYWORDS as the public name (union of both sets) for external consumers
REJECT_KEYWORDS: frozenset[str] = _SINGLE_WORD_REJECTS | frozenset(_PHRASE_REJECTS)

_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def build_query_string(
    card_name: str,
    set_code: Optional[str],
    is_foil: Optional[bool],
    frame: Optional[str],
) -> str:
    parts = [_PUNCTUATION_RE.sub("", card_name).strip()]
    if set_code:
        parts.append(set_code.upper())
    if is_foil is True:
        parts.append("foil")
    elif is_foil is False:
        parts.append("non-foil")
    if frame:
        parts.append(frame.lower().replace("_", " "))
    parts.append("MTG")
    return " ".join(parts)


def score_title(
    title: str,
    card_name: str,
    set_code: Optional[str],
    is_foil: Optional[bool],
    frame: Optional[str],
) -> float:
    lower = title.lower()

    # Normalize "nonfoil" → "non-foil" before all checks
    normalized = lower.replace("nonfoil", "non-foil")

    # Hard reject — single-word with boundaries, phrases as substrings
    for pattern in _REJECT_PATTERNS:
        if pattern.search(normalized):
            return 0.0
    for phrase in _PHRASE_REJECTS:
        if phrase in normalized:
            return 0.0

    score = 0.0

    # Card name words (0.50) — strip punctuation from both sides for fair comparison
    clean_name = _PUNCTUATION_RE.sub("", card_name).lower()
    clean_lower = _PUNCTUATION_RE.sub("", normalized)
    name_words = clean_name.split()
    if name_words and all(w in clean_lower for w in name_words):
        score += 0.50

    # Set code (0.20)
    if set_code and set_code.lower() in normalized:
        score += 0.20

    # Foil (0.15)
    if is_foil is True and "foil" in normalized and "non-foil" not in normalized:
        score += 0.15
    elif is_foil is False and "non-foil" in normalized:
        score += 0.15

    # Frame variant (0.15) — normalize underscore to space
    if frame:
        normalized_frame = frame.lower().replace("_", " ")
        if normalized_frame in normalized:
            score += 0.15

    return min(score, 1.0)
