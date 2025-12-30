import re
import unicodedata
import logging

logger = logging.getLogger(__name__)

SUPER_TYPES = {
    "Basic", "Elite", "Host", "Legendary", "Ongoing",
    "Snow", "World"
}

OBSOLETE_MAP = {
    "Continuous Artifact": "Artifact",
    "Interrupt": "Instant",
    "Local Enchantment": "Enchantment",
    "Mana Source": "Instant",
    "Mono Artifact": "Artifact",
    "Poly Artifact": "Artifact",
    "Summon": "Creature",
}

CARD_TYPES = {
    "Artifact", "Creature", "Enchantment", "Instant", "Land",
    "Planeswalker", "Sorcery", "Kindred", "Dungeon", "Battle",
    "Plane", "Phenomenon", "Vanguard", "Scheme", "Conspiracy", "Emblem", "Token"
}

DASH_RE = re.compile(r"\s*[—–-]\s*")  # normalize all dashes
PUNCT_RE = re.compile(r"[.,(){}\[\]\"';:]")

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = PUNCT_RE.sub("", text)
    return text.strip()

def process_type_line(card_type_line : str | None):

    # Normalize unicode + punctuation
    card_type_line = normalize(card_type_line)

    # Split main vs subtype using dash
    parts = DASH_RE.split(card_type_line, maxsplit=1)
    main_part = parts[0]
    subtype_part = parts[1] if len(parts) > 1 else None

    supertypes: list[str] = []
    types: list[str] = []
    subtypes: list[str] = []

    # Handle legacy full-line replacements first
    if card_type_line in OBSOLETE_MAP:
        return {
            "supertypes": [],
            "types": [OBSOLETE_MAP[card_type_line]],
            "subtypes": [],
        }

    # Parse main part
    for token in main_part.split():
        if token in SUPER_TYPES:
            supertypes.append(token)
        elif token in CARD_TYPES:
            types.append(token)
        elif token in OBSOLETE_MAP:
            types.append(OBSOLETE_MAP[token])
        # ignore unknown tokens here

    # Parse subtypes (space-separated, keep hyphenated words)
    if subtype_part:
        subtype_part = normalize(subtype_part)
        subtypes.extend(subtype_part.split())
    if not types:
        logger.warning("Unknown card type_line: %r", card_type_line)
    return {
        "supertypes": supertypes,
        "types": types,
        "subtypes": subtypes,
    }