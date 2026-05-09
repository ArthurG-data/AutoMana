import re
from typing import Optional

REJECT_KEYWORDS: frozenset[str] = frozenset({
    "proxy", "fake", "alter", "custom", "token", "lot", "playset",
    "bundle", "signed", "psa", "bgs", "cgc", "graded", "reprint lot",
})

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
        parts.append(frame.lower())
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

    # Hard reject
    for kw in REJECT_KEYWORDS:
        if kw in lower:
            return 0.0

    score = 0.0

    # Card name words (0.50)
    clean_name = _PUNCTUATION_RE.sub("", card_name).lower()
    name_words = clean_name.split()
    if name_words and all(w in lower for w in name_words):
        score += 0.50

    # Set code (0.20)
    if set_code and set_code.lower() in lower:
        score += 0.20

    # Foil (0.15)
    if is_foil is True and "foil" in lower and "non-foil" not in lower:
        score += 0.15
    elif is_foil is False and "non-foil" in lower:
        score += 0.15

    # Frame variant (0.15)
    if frame and frame.lower() in lower:
        score += 0.15

    return min(score, 1.0)
