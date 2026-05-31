"""Pure matching helpers for the PriceCharting pipeline.

These functions are deliberately side-effect free (no DB, no I/O) so they can be
unit-tested in isolation. They are the algorithmic core lifted from the notebook
prototype:

  * set name  -> DB set_code            (4-pass matcher + manual overrides)
  * PC product -> card_version_id        (treatment scoring + tiebreakers)
  * PC title  -> finish_id               (bracket-tag parsing)

The service layer does the DB fetches and JSON I/O and feeds the rows here.
"""
from __future__ import annotations

import difflib
import re

# ─────────────────────────────────────────────────────────────────────────────
# Set name normalisation + matching
# ─────────────────────────────────────────────────────────────────────────────

_ORDINAL_MAP = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th",
    "fifth": "5th", "sixth": "6th", "seventh": "7th", "eighth": "8th",
    "ninth": "9th", "tenth": "10th",
}

# Keyed by normalize_set_name(name) AFTER stripping the leading "magic " prefix.
NAME_OVERRIDES: dict[str, str] = {
    "ravnica": "rav",                      # Ravnica: City of Guilds
    "commander": "cmd",                    # Commander 2011 (ambiguous prefix)
    "lord of the rings": "ltr",            # Tales of Middle-earth main set
    "lord of the rings commander": "ltc",
    "lord of the rings art series": "altr",
    "warhammer 40,000": "40k",
    "summer edition": "sum",               # Summer Magic / Edgar
    "jurassic world": "rex",
    "beta": "leb",                         # Beta Edition (too short for prefix match)
    # ── recovered sets (PC name -> DB set_code) ──────────────────────────────
    "the list reprints": "plst",           # The List (3.7k singles); flat #N numbering
    "vintage masters": "vma",
    "the big score": "big",
    "masterpiece series amonkhet invocations": "mp2",
    "amonkhet invocations": "mp2",
    "guilds of ravnica guild kits": "gk1",
    "ravnica allegiance guild kits": "gk2",
}


def normalize_set_name(name: str) -> str:
    """Lower, strip leading 'the', drop colons/apostrophes, normalise ordinals,
    core-set aliases (m10 -> magic 2010), and the 'vs.' duel-deck separator."""
    n = name.lower().strip()
    n = re.sub(r"^the\s+", "", n)
    n = re.sub(r"[:'']", "", n)
    n = re.sub(r"\bvs\.", "vs", n)         # "Elves vs. Goblins" -> "elves vs goblins"
    n = re.sub(r"\s+", " ", n).strip()
    for word, num in _ORDINAL_MAP.items():
        n = re.sub(rf"\b{word}\b", num, n)
    n = re.sub(r"^limited edition\s+", "", n)
    n = re.sub(r"^classic\s+", "", n)
    n = re.sub(r"\bm(1[0-5])\b", lambda m: f"magic 20{m.group(1)}", n)
    return n


def build_set_code_index(db_sets: list[dict]) -> dict[str, str]:
    """Build {normalized_set_name: set_code} from DB rows (set_name, set_code)."""
    return {normalize_set_name(r["set_name"]): r["set_code"] for r in db_sets}


def match_set_code(pc_name: str, db_index: dict[str, str]) -> tuple[str | None, str | None]:
    """Map a PriceCharting set name to a DB set_code. Returns (set_code, method)
    or (None, None). Methods, in priority order: override, exact, suffix,
    prefix, fuzzy."""
    db_norms = list(db_index.keys())
    pc = normalize_set_name(pc_name)
    pc = re.sub(r"^magic\s+", "", pc)

    # Pass 0: manual override
    if pc in NAME_OVERRIDES:
        return NAME_OVERRIDES[pc], "override"

    # Pass 1: exact normalised name
    if pc in db_index:
        return db_index[pc], "exact"

    # Pass 1b: duel decks — PC drops the "Duel Decks[ Anthology]:" prefix.
    # "elves vs goblins" -> "duel decks elves vs goblins";
    # "anthology elves vs goblins" -> "duel decks anthology elves vs goblins".
    if " vs " in pc:
        if pc.startswith("anthology "):
            cand = "duel decks anthology " + pc[len("anthology "):]
        else:
            cand = "duel decks " + pc
        if cand in db_index:
            return db_index[cand], "duel_deck"

    # Pass 2: DB name is a suffix of PC name (>= 3 words) — Commander precons
    for dn in db_norms:
        if len(dn.split()) >= 3 and pc.endswith(" " + dn):
            return db_index[dn], "suffix"

    # Pass 3: PC name is a strict prefix of a DB name (>= 6 chars); shortest wins
    prefix_hits = [dn for dn in db_norms if len(pc) >= 6 and dn.startswith(pc + " ")]
    if prefix_hits:
        return db_index[min(prefix_hits, key=len)], "prefix"

    # Pass 4: fuzzy (ratio >= 0.82)
    close = difflib.get_close_matches(pc, db_norms, n=1, cutoff=0.82)
    if close:
        return db_index[close[0]], "fuzzy"

    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Finish parsing (PC title bracket -> finish_id)
# ─────────────────────────────────────────────────────────────────────────────

_ETCHED_RE = re.compile(r"\betched\b", re.I)
_FOIL_RE = re.compile(r"\bfoil\b", re.I)


def extract_bracket_tag(title: str) -> str:
    """Return the contents of the first ``[...]`` bracket, or ''."""
    m = re.search(r"\[([^\]]+)\]", title)
    return m.group(1) if m else ""


def parse_finish(title: str) -> int:
    """finish_id: 3 = etched, 2 = foil/prerelease, 1 = non-foil."""
    tag = extract_bracket_tag(title)
    if _ETCHED_RE.search(tag):
        return 3
    if _FOIL_RE.search(tag) or _FOIL_RE.search(title):
        return 2
    if "prerelease" in tag.lower():
        return 2
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Treatment scoring + card_version resolution
# ─────────────────────────────────────────────────────────────────────────────

# Finish words are stripped from the bracket before scoring so "[Showcase Foil]"
# scores on "showcase" only.
_FINISH_WORDS_RE = re.compile(
    r"\b(compleat\s+foil|etched\s+foil|textured\s+foil|galaxy\s+foil|"
    r"surge\s+foil|gilded\s+foil|oil\s+slick\s+foil|rainbow\s+foil|"
    r"halo\s+foil|neon\s+ink\s+foil|dazzle\s+foil|non.?foil|foil)\b",
    re.I,
)

_TREATMENT_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"showcase", re.I), "showcase"),
    (re.compile(r"extended.?art", re.I), "extendedart"),
    (re.compile(r"full.?art", re.I), "fullart"),
    (re.compile(r"borderless", re.I), "borderless"),
    (re.compile(r"etched", re.I), "etched"),
    (re.compile(r"inverted|phyrexian", re.I), "inverted"),
    (re.compile(r"dazzle", re.I), "dazzlefoil"),
    (re.compile(r"shattered.?glass", re.I), "shatteredglass"),
    (re.compile(r"textless", re.I), "textless"),
    (re.compile(r"colorshifted", re.I), "colorshifted"),
]


def score_candidate(row: dict, bracket_tag: str) -> int:
    """+3 when the bracket signals a treatment the candidate has, -2 when it
    signals one the candidate lacks."""
    fe = {e.lower() for e in (row.get("frame_effects") or [])}
    bc = (row.get("border_color_name") or "").lower()
    fua = bool(row.get("full_art", False))

    def has(signal: str) -> bool:
        if signal == "borderless":
            return bc == "borderless"
        if signal == "fullart":
            return "fullart" in fe or fua
        return signal in fe

    score = 0
    for pattern, signal in _TREATMENT_MAP:
        if pattern.search(bracket_tag):
            score += 3 if has(signal) else -2
    return score


def _collector_int(collector_number: str | None) -> int:
    try:
        return int(re.sub(r"[^0-9]", "", collector_number or "9999"))
    except ValueError:
        return 9999


def extract_collector_number(title: str) -> str | None:
    """The ``#NNN`` collector token from a PC title (e.g. ``#315``, ``#291a``)."""
    m = re.search(r"#(\d+[a-zA-Z★]*)", title)
    return m.group(1) if m else None


# Base certainty (0-100) by the signal that singled out the winner.
_CERTAINTY = {
    "tcg": 95,          # winner's tcgplayer_id == the scraped (consensus) id
    "collector": 85,    # collector #NNN pinned to exactly one candidate
    "name": 80,         # only one candidate by name
    "treatment": 65,    # treatment scoring broke a tie
    "ambiguous": 40,    # fell through to lowest-collector
}


def resolve_card_match(
    candidates: list[dict],
    title: str,
    pc_tcgplayer_id: str | None,
    set_method: str = "exact",
    tcg_votes: int = 0,
) -> dict | None:
    """Pick the winning card_version from name-match candidates and score it.

    Selection order:
      0. collector-number filter — if the title has ``#NNN`` and any candidate
         shares it, restrict to those (the doc's "Pass 1"; strongest signal).
    Then, while >1 candidate remains:
      1. treatment score (highest, if any positive)
      2. scraped (consensus) TCGPlayer id == candidate tcgplayer_id (unique hit)
      3. lowest collector number (ambiguous fallback)

    Returns {card_version_id, card_name, collector_number, finish_id,
    match_method, certainty} or None. ``certainty`` (0-100) reflects how
    decisively the winner was singled out, the TCGPlayer-id confirmation and
    its vote count, and whether the set itself matched fuzzily.
    """
    if not candidates:
        return None

    winners = list(candidates)
    tag = extract_bracket_tag(title)
    n_candidates = len(candidates)

    collector = extract_collector_number(title)
    collector_pinned = False
    if collector:
        by_collector = [r for r in winners if r.get("collector_number") == collector]
        if by_collector:
            winners = by_collector
            collector_pinned = len(winners) == 1

    if len(winners) > 1:
        clean_tag = _FINISH_WORDS_RE.sub("", tag).strip()
        scored = [(r, score_candidate(r, clean_tag)) for r in winners]
        top = max(s for _, s in scored)
        if top > 0:
            winners = [r for r, s in scored if s == top]
        treatment_used = len(winners) == 1
    else:
        treatment_used = False

    tcg_used = False
    if len(winners) > 1 and pc_tcgplayer_id:
        tcg_hits = [r for r in winners if str(r.get("tcgplayer_id")) == str(pc_tcgplayer_id)]
        if len(tcg_hits) == 1:
            winners = tcg_hits
            tcg_used = True

    ambiguous = len(winners) > 1
    if ambiguous:
        winners = sorted(winners, key=lambda r: _collector_int(r.get("collector_number")))

    w = winners[0]

    # ── derive method + certainty ────────────────────────────────────────────
    tcg_confirmed = bool(
        pc_tcgplayer_id and str(w.get("tcgplayer_id")) == str(pc_tcgplayer_id)
    )
    if tcg_used or tcg_confirmed:
        method = "tcg"
    elif n_candidates == 1:
        method = "name"
    elif collector_pinned:
        method = "collector"
    elif treatment_used:
        method = "treatment"
    elif ambiguous:
        method = "ambiguous"
    else:
        method = "collector" if collector else "name"

    certainty = _CERTAINTY.get(method, 50)
    if tcg_confirmed and tcg_votes >= 5:
        certainty = min(99, certainty + 3)     # strong consensus on the id
    if set_method in ("fuzzy", "prefix"):
        certainty = max(20, certainty - 20)    # set itself matched loosely

    return {
        "card_version_id": str(w["card_version_id"]),
        "card_name": w.get("card_name"),
        "collector_number": w.get("collector_number"),
        "finish_id": parse_finish(title),
        "match_method": method,
        "certainty": certainty,
    }


def clean_card_name(title: str) -> str:
    """Strip the ``[...]`` treatment bracket and the ``#NNN`` collector token
    from a PriceCharting product title to get the bare card name."""
    name = re.sub(r"\s*\[.*?\]", "", title).strip()
    name = re.sub(r"\s*#\d+\S*", "", name).strip()
    return name
