# eBay Global Market Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nightly pipeline that scrapes sold MTG card prices from eBay US, AU, and CA markets with full finish/condition/frame enrichment, storing native currencies (USD/AUD/CAD) with daily FX rates for query-time normalisation.

**Architecture:** A configurable watchlist (`pricing.ebay_scrape_targets`) auto-populated from rare/mythic/promo cards above $1 drives nightly Finding API calls across three marketplaces. Title parsing extracts finish and condition from listing text. Prices land in the existing `pricing.ebay_scraped_sold` staging table (extended with `marketplace_id`) and are promoted to `pricing.price_observation` by the existing `promote_sold_obs` beat. FX rates fetched from `frankfurter.app` normalise AU/CA prices to USD at query time.

**Tech Stack:** Python 3.12, asyncio, asyncpg, httpx, TimescaleDB, eBay Finding API (no user OAuth — App ID only)

---

## File Map

**Create:**
- `database/SQL/migrations/migration_45_ebay_global_market_scraper.sql`
- `core/services/app_integration/ebay/title_parser.py`
- `core/services/pricing/fetch_fx_rates_service.py`
- `core/services/app_integration/ebay/refresh_scrape_targets_service.py`
- `core/services/app_integration/ebay/scrape_global_market_service.py`
- `core/repositories/pricing/fx_rates_repository.py`
- `tests/unit/core/services/app_integration/ebay/test_title_parser.py`
- `tests/unit/core/services/pricing/test_fetch_fx_rates_service.py`
- `tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py`

**Modify:**
- `core/repositories/app_integration/ebay/ApiFinding_repository.py` — add `global_id` param
- `core/repositories/app_integration/ebay/ebay_scrape_queries.py` — add marketplace_id to INSERT; add scrape target queries
- `core/repositories/app_integration/ebay/ebay_scrape_repository.py` — add `marketplace_id` to `insert_scraped_sold`; add scrape target methods
- `core/repositories/card_catalog/card_repository.py` — add `get_scrape_metadata` method
- `worker/celeryconfig.py` — 3 new beat entries

---

## Task 1: DB Migration 45

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_45_ebay_global_market_scraper.sql`

- [ ] **Step 1: Write the migration**

```sql
BEGIN;

-- 1. Watchlist: cards to scrape across all markets nightly.
CREATE TABLE IF NOT EXISTS pricing.ebay_scrape_targets (
    card_version_id  UUID         PRIMARY KEY
        REFERENCES card_catalog.card_version(card_version_id),
    added_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_scraped_at  TIMESTAMPTZ,
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    added_by         TEXT         NOT NULL DEFAULT 'auto'
);

GRANT SELECT, INSERT, UPDATE ON pricing.ebay_scrape_targets
    TO app_backend, app_celery;

-- 2. Daily FX rates for AUD→USD and CAD→USD normalisation.
CREATE TABLE IF NOT EXISTS pricing.fx_rates (
    rate_date      DATE          NOT NULL,
    from_currency  VARCHAR(3)    NOT NULL,
    to_currency    VARCHAR(3)    NOT NULL DEFAULT 'USD',
    rate           NUMERIC(12,6) NOT NULL,
    fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, from_currency, to_currency)
);

GRANT SELECT, INSERT, UPDATE ON pricing.fx_rates
    TO app_backend, app_celery;

-- 3. Tag each scraped sold row with its source eBay marketplace.
ALTER TABLE pricing.ebay_scraped_sold
    ADD COLUMN IF NOT EXISTS marketplace_id VARCHAR(20) NOT NULL DEFAULT 'EBAY-US';

COMMIT;
```

- [ ] **Step 2: Apply migration to dev DB**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
  < src/automana/database/SQL/migrations/migration_45_ebay_global_market_scraper.sql
```

Expected: `BEGIN`, `CREATE TABLE`, `GRANT`, `CREATE TABLE`, `GRANT`, `ALTER TABLE`, `COMMIT` — no errors.

- [ ] **Step 3: Verify tables exist**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "\d pricing.ebay_scrape_targets; \d pricing.fx_rates; \d pricing.ebay_scraped_sold" | grep -E "marketplace_id|ebay_scrape_targets|fx_rates"
```

Expected: all three objects visible, `marketplace_id` column on `ebay_scraped_sold`.

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_45_ebay_global_market_scraper.sql
git commit -m "feat(db): migration 45 — ebay_scrape_targets, fx_rates, ebay_scraped_sold.marketplace_id"
```

---

## Task 2: Finding API — Add `global_id` Parameter

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py`
- Test: `tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py`

- [ ] **Step 1: Write a failing test**

Add to `tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
)


@pytest.mark.asyncio
async def test_find_completed_items_passes_global_id_to_params():
    repo = EbayFindingAPIRepository(environment="sandbox")
    fake_response = {
        "findCompletedItemsResponse": [{
            "ack": ["Success"],
            "searchResult": [{"item": [], "@count": "0"}],
        }]
    }
    with patch.object(repo, "send", new_callable=AsyncMock) as mock_send, \
         patch.object(repo, "_parse_response", return_value=fake_response), \
         patch.object(repo, "__aenter__", return_value=repo), \
         patch.object(repo, "__aexit__", return_value=False):
        mock_send.return_value = MagicMock()
        await repo.find_completed_items(
            keywords="Sheoldred MH2 MTG",
            app_id="TestApp-123",
            global_id="EBAY-AU",
        )
    call_params = mock_send.call_args[1]["params"]
    assert call_params.get("GLOBAL-ID") == "EBAY-AU"


@pytest.mark.asyncio
async def test_find_completed_items_defaults_global_id_to_us():
    repo = EbayFindingAPIRepository(environment="sandbox")
    fake_response = {
        "findCompletedItemsResponse": [{
            "ack": ["Success"],
            "searchResult": [{"item": [], "@count": "0"}],
        }]
    }
    with patch.object(repo, "send", new_callable=AsyncMock) as mock_send, \
         patch.object(repo, "_parse_response", return_value=fake_response), \
         patch.object(repo, "__aenter__", return_value=repo), \
         patch.object(repo, "__aexit__", return_value=False):
        mock_send.return_value = MagicMock()
        await repo.find_completed_items(
            keywords="Sheoldred MH2 MTG",
            app_id="TestApp-123",
        )
    call_params = mock_send.call_args[1]["params"]
    assert call_params.get("GLOBAL-ID") == "EBAY-US"
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd /home/arthur/projects/AutoMana
python -m pytest tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py \
  -k "global_id" -v 2>&1 | tail -20
```

Expected: `FAILED` — `AssertionError` (key not in params yet).

- [ ] **Step 3: Add `global_id` to `find_completed_items`**

In `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py`, update the method signature and params dict:

```python
async def find_completed_items(
    self,
    keywords: str,
    app_id: str,
    *,
    global_id: str = "EBAY-US",      # ← new param
    category_id: int = 2536,
    condition_id: Optional[int] = None,
    min_date: Optional[datetime] = None,
    limit: int = 50,
) -> list[dict]:
    params: dict[str, Any] = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": _SERVICE_VERSION,
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "GLOBAL-ID": global_id,            # ← new line
        "keywords": keywords,
        "categoryId": str(category_id),
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "paginationInput.entriesPerPage": str(min(limit, 100)),
        "paginationInput.pageNumber": "1",
    }
    # rest of method unchanged
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py \
  -k "global_id" -v 2>&1 | tail -10
```

Expected: both tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py \
        tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py
git commit -m "feat(ebay): add global_id param to Finding API find_completed_items"
```

---

## Task 3: `title_parser.py` — Finish and Condition Parsing

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/title_parser.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_title_parser.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/core/services/app_integration/ebay/test_title_parser.py`:

```python
import pytest
from automana.core.services.app_integration.ebay.title_parser import (
    parse_finish_code,
    parse_condition_code,
    FINISH_ID_MAP,
    CONDITION_ID_MAP,
)


# --- parse_finish_code ---

@pytest.mark.parametrize("title,expected", [
    ("Sheoldred the Apocalypse Surge Foil NM MH2", "SURGE_FOIL"),
    ("Sheoldred Ripple Foil NM MH2 MTG", "RIPPLE_FOIL"),
    ("Sheoldred Rainbow Foil NM MH2", "RAINBOW_FOIL"),
    ("Sheoldred Etched Foil NM MH2", "ETCHED"),
    ("Sheoldred Foil Etched NM MH2", "ETCHED"),
    ("Sheoldred Foil NM MH2 MTG", "FOIL"),
    ("Sheoldred NM MH2 MTG", "NONFOIL"),
    ("Sheoldred Non-Foil NM MH2 MTG", "NONFOIL"),
    ("Sheoldred Nonfoil NM MH2 MTG", "NONFOIL"),
    ("SHEOLDRED FOIL NM MH2", "FOIL"),          # case insensitive
])
def test_parse_finish_code(title, expected):
    assert parse_finish_code(title) == expected


# --- parse_condition_code ---

@pytest.mark.parametrize("ebay_cond,title,expected", [
    ("Near Mint or Better", "", "NM"),
    ("Lightly Played", "", "LP"),
    ("Moderately Played", "", "MP"),
    ("Heavily Played", "", "HP"),
    ("Damaged", "", "DMG"),
    (None, "Sheoldred NM Foil MH2", "NM"),
    (None, "Sheoldred LP Showcase MH2", "LP"),
    (None, "Sheoldred SP MH2 MTG", "SP"),
    (None, "Sheoldred MP MH2 MTG", "MP"),
    (None, "Sheoldred HP MH2 MTG", "HP"),
    (None, "Sheoldred PLD MH2 MTG", "HP"),
    (None, "Sheoldred Damaged MH2", "DMG"),
    (None, "Sheoldred MTG card no condition", "NM"),   # default
    ("", "Sheoldred MTG card no condition", "NM"),     # empty ebay string → default
])
def test_parse_condition_code(ebay_cond, title, expected):
    assert parse_condition_code(ebay_cond, title) == expected


# --- ID maps are complete ---

def test_finish_id_map_covers_all_codes():
    for code in ("NONFOIL", "FOIL", "ETCHED", "SURGE_FOIL", "RIPPLE_FOIL", "RAINBOW_FOIL"):
        assert code in FINISH_ID_MAP

def test_condition_id_map_covers_all_codes():
    for code in ("NM", "LP", "SP", "MP", "HP", "DMG"):
        assert code in CONDITION_ID_MAP
```

- [ ] **Step 2: Run to confirm fail**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_title_parser.py -v 2>&1 | tail -10
```

Expected: `ERROR` — module not found.

- [ ] **Step 3: Implement `title_parser.py`**

Create `src/automana/core/services/app_integration/ebay/title_parser.py`:

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_title_parser.py -v 2>&1 | tail -20
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/title_parser.py \
        tests/unit/core/services/app_integration/ebay/test_title_parser.py
git commit -m "feat(ebay): add title_parser — finish and condition extraction from eBay titles"
```

---

## Task 4: `title_parser.py` — Frame Variant and Conflict Detection

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/title_parser.py`
- Modify: `tests/unit/core/services/app_integration/ebay/test_title_parser.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/unit/core/services/app_integration/ebay/test_title_parser.py`:

```python
from automana.core.services.app_integration.ebay.title_parser import (
    parse_frame_variant,
    conflicts_with_expected,
)


# --- parse_frame_variant ---

@pytest.mark.parametrize("title,expected_key,expected_val", [
    ("Sheoldred Showcase Foil NM MH2",   "frame_effects",  ["showcase"]),
    ("Sheoldred Extended Art NM MH2",    "frame_effects",  ["extendedart"]),
    ("Sheoldred Ext Art NM MH2",         "frame_effects",  ["extendedart"]),
    ("Sheoldred EA NM MH2",              "frame_effects",  ["extendedart"]),
    ("Sheoldred Borderless NM MH2",      "is_borderless",  True),
    ("Sheoldred Retro Frame NM MH2",     "frame_effects",  ["retro"]),
    ("Sheoldred Old Border NM MH2",      "frame_effects",  ["retro"]),
    ("Sheoldred Full Art NM MH2",        "is_full_art",    True),
    ("Sheoldred Promo Pack NM MH2",      "promo_types",    ["promopack"]),
    ("Sheoldred Prerelease NM MH2",      "promo_types",    ["prerelease"]),
    ("Sheoldred Buy a Box NM MH2",       "promo_types",    ["buyabox"]),
    ("Sheoldred NM MH2 MTG",            "frame_effects",  []),  # no signals
])
def test_parse_frame_variant(title, expected_key, expected_val):
    result = parse_frame_variant(title)
    assert result[expected_key] == expected_val


# --- conflicts_with_expected ---

def test_no_conflict_when_title_has_no_frame_signal():
    """Permissive: title without frame signal never conflicts."""
    parsed = {"frame_effects": [], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": ["showcase"], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is False


def test_conflict_when_title_showcase_but_card_is_regular():
    parsed = {"frame_effects": ["showcase"], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": [], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is True


def test_conflict_when_title_borderless_but_card_is_not():
    parsed = {"frame_effects": [], "is_borderless": True, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": [], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is True


def test_no_conflict_when_both_showcase():
    parsed = {"frame_effects": ["showcase"], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": ["showcase"], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is False


def test_no_conflict_when_card_regular_title_has_no_signal():
    parsed = {"frame_effects": [], "is_borderless": False, "is_full_art": False, "promo_types": []}
    card = {"frame_effects": [], "border_color_name": "black", "full_art": False, "is_promo": False, "promo_types": []}
    assert conflicts_with_expected(parsed, card) is False
```

- [ ] **Step 2: Run to confirm fail**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_title_parser.py \
  -k "frame_variant or conflict" -v 2>&1 | tail -10
```

Expected: `ERROR` — `parse_frame_variant` not found.

- [ ] **Step 3: Add `parse_frame_variant` and `conflicts_with_expected` to `title_parser.py`**

Append to the bottom of `src/automana/core/services/app_integration/ebay/title_parser.py`:

```python
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
```

- [ ] **Step 4: Run all title_parser tests**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_title_parser.py -v 2>&1 | tail -20
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/title_parser.py \
        tests/unit/core/services/app_integration/ebay/test_title_parser.py
git commit -m "feat(ebay): add parse_frame_variant and conflicts_with_expected to title_parser"
```

---

## Task 5: Card Repository — `get_scrape_metadata`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py`
- Test: `tests/unit/core/repositories/card_catalog/` (new test or append to existing)

The existing `card_repository.get()` does not return `frame_effects`, `is_promo`,
`border_color_name`, or `full_art`. Add a focused method for the global market scraper.

- [ ] **Step 1: Write failing test**

Create `tests/unit/core/repositories/card_catalog/test_card_scrape_metadata.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository


@pytest.mark.asyncio
async def test_get_scrape_metadata_returns_expected_fields():
    mock_conn = AsyncMock()
    repo = CardReferenceRepository(connection=mock_conn, executor=None)
    card_id = uuid4()
    fake_row = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": ["showcase"],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    # execute_query returns a list of mappings; dict(row) must work.
    # Use a plain dict directly — asyncpg Records support dict() via __iter__.
    with patch.object(repo, "execute_query", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = [fake_row]
        result = await repo.get_scrape_metadata(card_id)

    assert result is not None
    assert result["card_name"] == "Sheoldred, the Apocalypse"
    assert result["frame_effects"] == ["showcase"]
    assert result["border_color_name"] == "black"


@pytest.mark.asyncio
async def test_get_scrape_metadata_returns_none_when_not_found():
    mock_conn = AsyncMock()
    repo = CardReferenceRepository(connection=mock_conn, executor=None)
    with patch.object(repo, "execute_query", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = []
        result = await repo.get_scrape_metadata(uuid4())
    assert result is None
```

- [ ] **Step 2: Run to confirm fail**

```bash
python -m pytest tests/unit/core/repositories/card_catalog/test_card_scrape_metadata.py -v 2>&1 | tail -10
```

Expected: `FAILED` — `AttributeError: 'CardReferenceRepository' object has no attribute 'get_scrape_metadata'`.

- [ ] **Step 3: Add `get_scrape_metadata` to `CardReferenceRepository`**

Add this method to `src/automana/core/repositories/card_catalog/card_repository.py` (after the existing `get` method):

```python
async def get_scrape_metadata(self, card_version_id: UUID) -> dict | None:
    """Return frame/promo attributes needed by the global market scraper."""
    query = """
        SELECT
            v.card_name,
            v.set_code,
            v.frame_effects,
            v.is_promo,
            v.promo_types,
            v.border_color_name,
            v.full_art
        FROM card_catalog.v_card_versions_complete v
        WHERE v.card_version_id = $1;
    """
    result = await self.execute_query(query, (card_version_id,))
    if not result:
        return None
    return dict(result[0])
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/unit/core/repositories/card_catalog/test_card_scrape_metadata.py -v 2>&1 | tail -10
```

Expected: tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py \
        tests/unit/core/repositories/card_catalog/test_card_scrape_metadata.py
git commit -m "feat(card): add get_scrape_metadata to CardReferenceRepository"
```

---

## Task 6: Scrape Repository — Add `marketplace_id` + Target Methods

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/ebay_scrape_repository.py`

- [ ] **Step 1: Update SQL queries**

Replace the entire content of `src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py`:

```python
"""SQL queries for EbayScrapeSoldRepository."""

INSERT_SCRAPED_SOLD = """
INSERT INTO pricing.ebay_scraped_sold
    (item_id, title, source_product_id, price_cents, currency, marketplace_id,
     condition_id, finish_id, language_id, sold_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (item_id) DO NOTHING;
"""

GET_UNPROMOTED_SCRAPED = """
SELECT scrape_id, source_product_id, price_cents, sold_at,
       finish_id, condition_id, language_id
FROM pricing.ebay_scraped_sold
WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;
"""

MARK_SCRAPED_PROMOTED = """
UPDATE pricing.ebay_scraped_sold
SET promoted_to_obs = true
WHERE scrape_id = ANY($1::bigint[]);
"""

GET_SCRAPE_TARGETS = """
SELECT card_version_id
FROM pricing.ebay_scrape_targets
WHERE is_active = true
ORDER BY last_scraped_at NULLS FIRST;
"""

REFRESH_SCRAPE_TARGETS = """
INSERT INTO pricing.ebay_scrape_targets (card_version_id, added_by)
SELECT DISTINCT cv.card_version_id, 'auto'
FROM card_catalog.v_card_versions_complete cv
JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
JOIN pricing.source_product sp ON sp.product_id = mcp.product_id
JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
WHERE (cv.rarity_name IN ('mythic', 'rare', 'special') OR cv.is_promo = true)
  AND po.sell_avg_cents >= $1
  AND po.ts_date >= now() - interval '7 days'
ON CONFLICT (card_version_id) DO UPDATE SET is_active = true;
"""

UPDATE_TARGET_LAST_SCRAPED = """
UPDATE pricing.ebay_scrape_targets
SET last_scraped_at = now()
WHERE card_version_id = $1;
"""
```

- [ ] **Step 2: Update `EbayScrapeSoldRepository`**

Replace the entire content of `src/automana/core/repositories/app_integration/ebay/ebay_scrape_repository.py`:

```python
"""DB repository for eBay sold-price persistence (external scrape channel)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)
from automana.core.repositories.app_integration.ebay import ebay_scrape_queries

logger = logging.getLogger(__name__)


class EbayScrapeSoldRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "EbayScrapeSoldRepository"

    async def add(self, item=None) -> None:
        pass

    async def get(self, id=None):
        return None

    async def update(self, item=None) -> None:
        pass

    async def delete(self, id=None) -> None:
        pass

    async def list(self, items=None) -> list:
        return []

    async def insert_scraped_sold(
        self,
        item_id: str,
        title: str,
        source_product_id: Optional[int],
        price_cents: int,
        currency: str,
        marketplace_id: str,
        condition_id: int,
        finish_id: int,
        language_id: int,
        sold_at: datetime,
    ) -> None:
        await self.execute_command(
            ebay_scrape_queries.INSERT_SCRAPED_SOLD,
            (
                item_id,
                title,
                source_product_id,
                price_cents,
                currency,
                marketplace_id,
                condition_id,
                finish_id,
                language_id,
                sold_at,
            ),
        )

    async def get_unpromoted(self) -> list[dict]:
        rows = await self.execute_query(
            ebay_scrape_queries.GET_UNPROMOTED_SCRAPED, ()
        )
        return [dict(r) for r in rows]

    async def mark_promoted(self, scrape_ids: list[int]) -> None:
        if not scrape_ids:
            return
        await self.execute_command(
            ebay_scrape_queries.MARK_SCRAPED_PROMOTED,
            (scrape_ids,),
        )

    async def get_scrape_targets(self) -> list[UUID]:
        rows = await self.execute_query(ebay_scrape_queries.GET_SCRAPE_TARGETS, ())
        return [UUID(str(r["card_version_id"])) for r in rows]

    async def refresh_scrape_targets(self, min_cents: int) -> None:
        await self.execute_command(
            ebay_scrape_queries.REFRESH_SCRAPE_TARGETS, (min_cents,)
        )

    async def update_target_last_scraped(self, card_version_id: UUID) -> None:
        await self.execute_command(
            ebay_scrape_queries.UPDATE_TARGET_LAST_SCRAPED, (str(card_version_id),)
        )
```

- [ ] **Step 3: Fix the existing `scrape_sold_service.py` call**

The existing `scrape_external_sold` service calls `insert_scraped_sold` without `marketplace_id`. Update it to pass the default:

In `src/automana/core/services/app_integration/ebay/scrape_sold_service.py`, find the `insert_scraped_sold` call and add `marketplace_id="EBAY-US"`:

```python
        await ebay_scrape_repository.insert_scraped_sold(
            item_id=item_id,
            title=title,
            source_product_id=source_product_id,
            price_cents=price_cents,
            currency=currency,
            marketplace_id="EBAY-US",   # ← add this
            condition_id=None,
            finish_id=1,
            language_id=1,
            sold_at=sold_at,
        )
```

- [ ] **Step 4: Run existing scrape tests to confirm nothing broke**

```bash
python -m pytest tests/unit/core/repositories/pricing/test_ebay_scrape_repository.py \
                 tests/unit/core/services/ebay/test_scrape_sold_service.py -v 2>&1 | tail -15
```

Expected: all existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ebay_scrape_queries.py \
        src/automana/core/repositories/app_integration/ebay/ebay_scrape_repository.py \
        src/automana/core/services/app_integration/ebay/scrape_sold_service.py
git commit -m "feat(ebay): add marketplace_id to ebay_scraped_sold inserts; add scrape target repo methods"
```

---

## Task 7: FX Rates Repository + `fetch_fx_rates` Service

**Files:**
- Create: `src/automana/core/repositories/pricing/fx_rates_repository.py`
- Create: `src/automana/core/services/pricing/fetch_fx_rates_service.py`
- Create: `tests/unit/core/services/pricing/test_fetch_fx_rates_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/core/services/pricing/test_fetch_fx_rates_service.py`:

```python
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from automana.core.services.pricing.fetch_fx_rates_service import fetch_fx_rates


@pytest.mark.asyncio
async def test_fetch_fx_rates_upserts_aud_and_cad():
    mock_repo = AsyncMock()
    fake_api_response = {"base": "USD", "date": "2026-05-22", "rates": {"AUD": 1.58, "CAD": 1.36}}

    with patch(
        "automana.core.services.pricing.fetch_fx_rates_service._fetch_rates_from_api",
        new_callable=AsyncMock,
        return_value=fake_api_response,
    ):
        result = await fetch_fx_rates(fx_rates_repository=mock_repo)

    assert mock_repo.upsert_rate.call_count == 2
    calls = {c.kwargs["from_currency"]: c.kwargs for c in mock_repo.upsert_rate.call_args_list}
    assert "AUD" in calls
    assert "CAD" in calls
    assert abs(calls["AUD"]["rate"] - (1 / 1.58)) < 0.0001
    assert abs(calls["CAD"]["rate"] - (1 / 1.36)) < 0.0001
    assert calls["AUD"]["to_currency"] == "USD"
    assert result["rates_upserted"] == 2


@pytest.mark.asyncio
async def test_fetch_fx_rates_handles_api_failure_gracefully():
    mock_repo = AsyncMock()

    with patch(
        "automana.core.services.pricing.fetch_fx_rates_service._fetch_rates_from_api",
        new_callable=AsyncMock,
        side_effect=Exception("network error"),
    ):
        result = await fetch_fx_rates(fx_rates_repository=mock_repo)

    mock_repo.upsert_rate.assert_not_called()
    assert result["rates_upserted"] == 0
```

- [ ] **Step 2: Run to confirm fail**

```bash
python -m pytest tests/unit/core/services/pricing/test_fetch_fx_rates_service.py -v 2>&1 | tail -10
```

Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `fx_rates_repository.py`**

Create `src/automana/core/repositories/pricing/fx_rates_repository.py`:

```python
"""DB repository for daily FX rates."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_UPSERT_RATE = """
INSERT INTO pricing.fx_rates (rate_date, from_currency, to_currency, rate)
VALUES ($1, $2, $3, $4)
ON CONFLICT (rate_date, from_currency, to_currency) DO UPDATE
    SET rate = EXCLUDED.rate, fetched_at = now();
"""


class FxRatesRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "FxRatesRepository"

    async def add(self, item=None) -> None:
        pass

    async def get(self, id=None):
        return None

    async def update(self, item=None) -> None:
        pass

    async def delete(self, id=None) -> None:
        pass

    async def list(self, items=None) -> list:
        return []

    async def upsert_rate(
        self,
        rate_date: date,
        from_currency: str,
        to_currency: str,
        rate: float,
    ) -> None:
        await self.execute_command(_UPSERT_RATE, (rate_date, from_currency, to_currency, rate))
```

- [ ] **Step 4: Create `fetch_fx_rates_service.py`**

Create `src/automana/core/services/pricing/fetch_fx_rates_service.py`:

```python
"""Nightly FX rate fetch — AUD→USD and CAD→USD from frankfurter.app."""
from __future__ import annotations

import logging
from datetime import date, timezone, datetime
from typing import Any

import httpx

from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
from automana.core.framework.registry import ServiceRegistry

logger = logging.getLogger(__name__)

_FRANKFURTER_URL = "https://api.frankfurter.app/latest"
_TARGET_CURRENCIES = ("AUD", "CAD")


async def _fetch_rates_from_api() -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _FRANKFURTER_URL,
            params={"from": "USD", "to": ",".join(_TARGET_CURRENCIES)},
        )
        resp.raise_for_status()
        return resp.json()


@ServiceRegistry.register(
    path="integrations.pricing.fetch_fx_rates",
    db_repositories=["fx_rates"],
    runs_in_transaction=False,
)
async def fetch_fx_rates(
    fx_rates_repository: FxRatesRepository,
    **kwargs: Any,
) -> dict:
    """Fetch daily USD→AUD and USD→CAD rates; store inverse (AUD→USD, CAD→USD)."""
    try:
        data = await _fetch_rates_from_api()
    except Exception:
        logger.exception("fetch_fx_rates_api_failed")
        return {"rates_upserted": 0}

    today = date.today()
    upserted = 0
    rates: dict = data.get("rates", {})

    for currency, usd_per_foreign in rates.items():
        if currency not in _TARGET_CURRENCIES:
            continue
        try:
            await fx_rates_repository.upsert_rate(
                rate_date=today,
                from_currency=currency,
                to_currency="USD",
                rate=1.0 / usd_per_foreign,   # AUD→USD = inverse of USD→AUD
            )
            upserted += 1
        except Exception:
            logger.exception("fetch_fx_rates_upsert_failed", extra={"currency": currency})

    logger.info("fetch_fx_rates_complete", extra={"rates_upserted": upserted})
    return {"rates_upserted": upserted}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/core/services/pricing/test_fetch_fx_rates_service.py -v 2>&1 | tail -15
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/pricing/fx_rates_repository.py \
        src/automana/core/services/pricing/fetch_fx_rates_service.py \
        tests/unit/core/services/pricing/test_fetch_fx_rates_service.py
git commit -m "feat(pricing): add FxRatesRepository and fetch_fx_rates service (frankfurter.app)"
```

---

## Task 8: `refresh_scrape_targets` Service

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/refresh_scrape_targets_service.py`

This service runs one SQL upsert via the repository method added in Task 6.
No dedicated test — covered by integration; the SQL is tested by its execution.

- [ ] **Step 1: Write failing test**

Create `tests/unit/core/services/app_integration/ebay/test_refresh_scrape_targets_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from automana.core.services.app_integration.ebay.refresh_scrape_targets_service import (
    refresh_scrape_targets,
)


@pytest.mark.asyncio
async def test_refresh_scrape_targets_calls_repo_with_min_cents():
    mock_repo = AsyncMock()
    with patch(
        "automana.core.services.app_integration.ebay.refresh_scrape_targets_service.get_settings",
        return_value=type("S", (), {"ebay_scrape_target_min_cents": 200})(),
    ):
        result = await refresh_scrape_targets(ebay_scrape_repository=mock_repo)

    mock_repo.refresh_scrape_targets.assert_called_once_with(min_cents=200)
    assert result["min_cents"] == 200


@pytest.mark.asyncio
async def test_refresh_scrape_targets_uses_default_when_setting_absent():
    mock_repo = AsyncMock()
    with patch(
        "automana.core.services.app_integration.ebay.refresh_scrape_targets_service.get_settings",
        return_value=type("S", (), {})(),   # no ebay_scrape_target_min_cents attr
    ):
        result = await refresh_scrape_targets(ebay_scrape_repository=mock_repo)

    mock_repo.refresh_scrape_targets.assert_called_once_with(min_cents=100)
    assert result["min_cents"] == 100
```

- [ ] **Step 2: Run to confirm fail**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_refresh_scrape_targets_service.py \
  -v 2>&1 | tail -10
```

Expected: `ERROR` — module not found.

- [ ] **Step 3: Create the service**

Create `src/automana/core/services/app_integration/ebay/refresh_scrape_targets_service.py`:

```python
"""Refresh the ebay_scrape_targets watchlist from rare/mythic/promo cards above a value threshold."""
from __future__ import annotations

import logging
from typing import Any

from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.framework.registry import ServiceRegistry
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_MIN_CENTS = 100   # $1.00 USD


@ServiceRegistry.register(
    path="integrations.ebay.refresh_scrape_targets",
    db_repositories=["ebay_scrape"],
    runs_in_transaction=False,
)
async def refresh_scrape_targets(
    ebay_scrape_repository: EbayScrapeSoldRepository,
    **kwargs: Any,
) -> dict:
    """Upsert rare/mythic/promo cards with sell_avg_cents >= threshold into ebay_scrape_targets."""
    settings = get_settings()
    min_cents = getattr(settings, "ebay_scrape_target_min_cents", _DEFAULT_MIN_CENTS)

    await ebay_scrape_repository.refresh_scrape_targets(min_cents=min_cents)
    logger.info("ebay_refresh_scrape_targets_complete", extra={"min_cents": min_cents})
    return {"status": "ok", "min_cents": min_cents}
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_refresh_scrape_targets_service.py \
  -v 2>&1 | tail -10
```

Expected: both tests `PASSED`.

- [ ] **Step 5: Confirm the service registry path resolves**

```bash
cd /home/arthur/projects/AutoMana
python -c "
from automana.core.services.app_integration.ebay.refresh_scrape_targets_service import refresh_scrape_targets
from automana.core.framework.registry import ServiceRegistry
svc = ServiceRegistry.get('integrations.ebay.refresh_scrape_targets')
print('registered:', svc is not None)
"
```

Expected: `registered: True`.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/refresh_scrape_targets_service.py \
        tests/unit/core/services/app_integration/ebay/test_refresh_scrape_targets_service.py
git commit -m "feat(ebay): add refresh_scrape_targets service — nightly watchlist upsert"
```

---

## Task 9: `scrape_global_market` Service

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from automana.core.services.app_integration.ebay.scrape_global_market_service import (
    _scrape_one_card,
)


def _make_item(title, price=5.0, currency="USD", condition=None, item_id=None):
    return {
        "item_id": item_id or "ITEM123",
        "title": title,
        "price": price,
        "currency": currency,
        "condition": condition,
        "sold_date": "2026-05-20T12:00:00.000Z",
    }


@pytest.mark.asyncio
async def test_scrape_one_card_inserts_foil_nm_correctly():
    card_version_id = uuid4()
    card = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    items = [_make_item("Sheoldred MH2 Foil NM MTG", condition="Near Mint or Better")]
    sales_repo = AsyncMock()
    sales_repo.ensure_product = AsyncMock(return_value=uuid4())
    sales_repo.ensure_source_product = AsyncMock(return_value=42)
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)

    count = await _scrape_one_card(
        card_version_id=card_version_id,
        card=card,
        app_id="APP-ID",
        marketplace="EBAY-US",
        min_date=MagicMock(),
        limit_per_card=50,
        score_threshold=0.7,
        ebay_sales_repository=sales_repo,
        ebay_scrape_repository=scrape_repo,
        ebay_finding_repository=finding_repo,
    )

    assert count == 1
    call_kwargs = scrape_repo.insert_scraped_sold.call_args.kwargs
    assert call_kwargs["finish_id"] == 2          # FOIL
    assert call_kwargs["condition_id"] == 1        # NM
    assert call_kwargs["marketplace_id"] == "EBAY-US"
    assert call_kwargs["currency"] == "USD"


@pytest.mark.asyncio
async def test_scrape_one_card_skips_low_score():
    card_version_id = uuid4()
    card = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    # Title completely unrelated — will score < 0.7
    items = [_make_item("Random Pokemon Card Charizard Holo")]
    sales_repo = AsyncMock()
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)

    count = await _scrape_one_card(
        card_version_id=card_version_id,
        card=card,
        app_id="APP-ID",
        marketplace="EBAY-US",
        min_date=MagicMock(),
        limit_per_card=50,
        score_threshold=0.7,
        ebay_sales_repository=sales_repo,
        ebay_scrape_repository=scrape_repo,
        ebay_finding_repository=finding_repo,
    )

    assert count == 0
    scrape_repo.insert_scraped_sold.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_one_card_skips_frame_conflict():
    """Title says 'showcase' but card has no frame effects → conflict → skip."""
    card_version_id = uuid4()
    card = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],          # regular version
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    items = [_make_item("Sheoldred MH2 Showcase Foil NM MTG")]
    sales_repo = AsyncMock()
    sales_repo.ensure_product = AsyncMock(return_value=uuid4())
    sales_repo.ensure_source_product = AsyncMock(return_value=42)
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)

    count = await _scrape_one_card(
        card_version_id=card_version_id,
        card=card,
        app_id="APP-ID",
        marketplace="EBAY-US",
        min_date=MagicMock(),
        limit_per_card=50,
        score_threshold=0.7,
        ebay_sales_repository=sales_repo,
        ebay_scrape_repository=scrape_repo,
        ebay_finding_repository=finding_repo,
    )

    assert count == 0
    scrape_repo.insert_scraped_sold.assert_not_called()
```

- [ ] **Step 2: Run to confirm fail**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py \
  -v 2>&1 | tail -10
```

Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `scrape_global_market_service.py`**

Create `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py`:

```python
"""eBay global market scraper — nightly sold-price collection across US, AU, CA markets.

Iterates pricing.ebay_scrape_targets, queries the eBay Finding API for each card
across three marketplaces, enriches results with finish/condition/frame parsing,
and inserts into pricing.ebay_scraped_sold.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
)
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.repositories.card_catalog.card_repository import (
    CardReferenceRepository,
)
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)
from automana.core.services.app_integration.ebay.title_parser import (
    CONDITION_ID_MAP,
    FINISH_ID_MAP,
    conflicts_with_expected,
    parse_condition_code,
    parse_finish_code,
    parse_frame_variant,
)
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_EBAY_SOURCE_ID = 5
_DEFAULT_LANGUAGE_ID = 1
_MARKETPLACES = ("EBAY-US", "EBAY-AU", "EBAY-ENCA")
_INTER_MARKETPLACE_DELAY = 0.3  # seconds between marketplace calls per card


@ServiceRegistry.register(
    path="integrations.ebay.scrape_global_market",
    db_repositories=["ebay_sales", "ebay_scrape", "card"],
    api_repositories=["ebay_finding"],
    runs_in_transaction=False,
)
async def scrape_global_market(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    card_repository: CardReferenceRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    days_back: int = 30,
    score_threshold: float = 0.7,
    limit_per_card: int = 50,
    **kwargs: Any,
) -> dict:
    """Scrape sold prices for watchlist cards across EBAY-US, EBAY-AU, EBAY-ENCA."""
    settings = get_settings()
    app_id = settings.ebay_app_id
    if not app_id:
        logger.warning("scrape_global_market_no_app_id")
        return {"scraped_items": 0, "cards_processed": 0}

    targets = await ebay_scrape_repository.get_scrape_targets()
    if not targets:
        logger.info("scrape_global_market_no_targets")
        return {"scraped_items": 0, "cards_processed": 0}

    min_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    total_items = 0

    for card_version_id in targets:
        card = await card_repository.get_scrape_metadata(card_version_id)
        if not card:
            logger.warning(
                "scrape_global_market_card_not_found",
                extra={"card_version_id": str(card_version_id)},
            )
            continue

        product_id = await ebay_sales_repository.ensure_product(card_version_id)
        if not product_id:
            logger.warning(
                "scrape_global_market_ensure_product_failed",
                extra={"card_version_id": str(card_version_id)},
            )
            continue

        source_product_id = await ebay_sales_repository.ensure_source_product(
            card_version_id, _EBAY_SOURCE_ID
        )
        if not source_product_id:
            logger.warning(
                "scrape_global_market_ensure_source_product_failed",
                extra={"card_version_id": str(card_version_id)},
            )
            continue

        for marketplace in _MARKETPLACES:
            try:
                count = await _scrape_one_card(
                    card_version_id=card_version_id,
                    card=card,
                    app_id=app_id,
                    marketplace=marketplace,
                    min_date=min_date,
                    limit_per_card=limit_per_card,
                    score_threshold=score_threshold,
                    ebay_sales_repository=ebay_sales_repository,
                    ebay_scrape_repository=ebay_scrape_repository,
                    ebay_finding_repository=ebay_finding_repository,
                    source_product_id=source_product_id,
                )
                total_items += count
            except Exception:
                logger.exception(
                    "scrape_global_market_card_marketplace_failed",
                    extra={
                        "card_version_id": str(card_version_id),
                        "marketplace": marketplace,
                    },
                )
            await asyncio.sleep(_INTER_MARKETPLACE_DELAY)

        try:
            await ebay_scrape_repository.update_target_last_scraped(card_version_id)
        except Exception:
            logger.warning(
                "scrape_global_market_update_last_scraped_failed",
                extra={"card_version_id": str(card_version_id)},
            )

    logger.info(
        "scrape_global_market_complete",
        extra={"scraped_items": total_items, "cards_processed": len(targets)},
    )
    return {"scraped_items": total_items, "cards_processed": len(targets)}


async def _scrape_one_card(
    card_version_id: UUID,
    card: dict,
    app_id: str,
    marketplace: str,
    min_date: datetime,
    limit_per_card: int,
    score_threshold: float,
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    source_product_id: Optional[int] = None,
) -> int:
    card_name: str = card.get("card_name", "")
    set_code: Optional[str] = card.get("set_code")
    frame_effects: list[str] = card.get("frame_effects") or []
    is_borderless: bool = (card.get("border_color_name") or "").lower() == "borderless"

    primary_frame = frame_effects[0] if frame_effects else (
        "borderless" if is_borderless else None
    )
    keywords = build_query_string(
        card_name=card_name,
        set_code=set_code,
        is_foil=None,
        frame=primary_frame,
    )

    items = await ebay_finding_repository.find_completed_items(
        keywords=keywords,
        app_id=app_id,
        global_id=marketplace,
        min_date=min_date,
        limit=limit_per_card,
    )

    # Resolve source_product_id if not pre-computed (called from tests directly).
    sp_id = source_product_id
    if sp_id is None:
        sp_id = await ebay_sales_repository.ensure_source_product(
            card_version_id, _EBAY_SOURCE_ID
        )
        if not sp_id:
            return 0

    count = 0
    for item in items:
        title: str = item.get("title", "")

        sc = score_title(title, card_name=card_name, set_code=set_code,
                         is_foil=None, frame=primary_frame)
        if sc < score_threshold:
            continue

        parsed_frame = parse_frame_variant(title)
        if conflicts_with_expected(parsed_frame, card):
            continue

        price_cents = _to_cents(item.get("price"))
        if price_cents is None:
            continue

        finish_code = parse_finish_code(title)
        finish_id = FINISH_ID_MAP.get(finish_code, 1)

        condition_code = parse_condition_code(item.get("condition"), title)
        condition_id = CONDITION_ID_MAP.get(condition_code, 1)

        currency: str = item.get("currency") or "USD"
        item_id: str = item.get("item_id") or ""
        sold_at = _parse_sold_date(item.get("sold_date"))

        await ebay_scrape_repository.insert_scraped_sold(
            item_id=item_id,
            title=title,
            source_product_id=sp_id,
            price_cents=price_cents,
            currency=currency,
            marketplace_id=marketplace,
            condition_id=condition_id,
            finish_id=finish_id,
            language_id=_DEFAULT_LANGUAGE_ID,
            sold_at=sold_at,
        )
        count += 1

    return count


def _to_cents(value: Any) -> Optional[int]:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _parse_sold_date(date_str: Optional[str]) -> datetime:
    if date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
```

- [ ] **Step 4: Run all scrape global market tests**

```bash
python -m pytest tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py \
  -v 2>&1 | tail -15
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/scrape_global_market_service.py \
        tests/unit/core/services/app_integration/ebay/test_scrape_global_market_service.py
git commit -m "feat(ebay): add scrape_global_market service — multi-marketplace sold price collection"
```

---

## Task 10: Wire Celery Beat Schedule

**Files:**
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 1: Ensure new service modules are imported by Celery**

Check that `automana.worker.tasks.pricing` includes the new services. Open
`src/automana/worker/tasks/pricing.py` and confirm it imports or references the
`fetch_fx_rates_service` module. If not, add the import so the `ServiceRegistry`
decorator runs at worker startup:

```python
# At top of src/automana/worker/tasks/pricing.py — add if not present:
import automana.core.services.pricing.fetch_fx_rates_service  # noqa: F401
```

Similarly, check `src/automana/worker/tasks/ebay.py` and add:

```python
import automana.core.services.app_integration.ebay.refresh_scrape_targets_service  # noqa: F401
import automana.core.services.app_integration.ebay.scrape_global_market_service    # noqa: F401
```

- [ ] **Step 2: Add 3 beat entries to `celeryconfig.py`**

In `src/automana/worker/celeryconfig.py`, find the `beat_schedule` dict and add after
the existing `pricing-health-hourly` entry:

```python
    # FX rates: fetch AUD→USD and CAD→USD from frankfurter.app before market scrape.
    "pricing-fetch-fx-rates-nightly": {
        "task": "run_service",
        "schedule": crontab(hour=6, minute=45),   # 06:45 AEST
        "kwargs": {"path": "integrations.pricing.fetch_fx_rates"},
    },
    # eBay global market: refresh rare/mythic/promo watchlist.
    "ebay-refresh-scrape-targets-nightly": {
        "task": "run_service",
        "schedule": crontab(hour=7, minute=0),    # 07:00 AEST
        "kwargs": {"path": "integrations.ebay.refresh_scrape_targets"},
    },
    # eBay global market: scrape sold prices across EBAY-US, EBAY-AU, EBAY-ENCA.
    "ebay-scrape-global-market-nightly": {
        "task": "run_service",
        "schedule": crontab(hour=7, minute=15),   # 07:15 AEST — after targets refreshed
        "kwargs": {
            "path": "integrations.ebay.scrape_global_market",
            "days_back": 30,
            "score_threshold": 0.7,
            "limit_per_card": 50,
        },
    },
    # existing promote_sold_obs at 08:00 picks up global market rows automatically
```

- [ ] **Step 3: Verify Celery can load the config**

```bash
cd /home/arthur/projects/AutoMana
python -c "
import automana.worker.celeryconfig as cfg
keys = [k for k in cfg.beat_schedule if 'fx-rates' in k or 'global-market' in k or 'scrape-targets' in k]
print('New beat entries:', keys)
"
```

Expected: prints all 3 new key names.

- [ ] **Step 4: Run full test suite to catch any regressions**

```bash
python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: all tests pass. Fix any failures before continuing.

- [ ] **Step 5: Final commit**

```bash
git add src/automana/worker/celeryconfig.py \
        src/automana/worker/tasks/pricing.py \
        src/automana/worker/tasks/ebay.py
git commit -m "feat(celery): wire fetch_fx_rates, refresh_scrape_targets, scrape_global_market to beat schedule"
```

---

## Done

All 10 tasks complete. The feature is ready for a PR from `feat/ebay-global-market-scraper` → `dev`.

The `promote_sold_obs` beat at 08:00 AEST already picks up global market rows from `ebay_scraped_sold` — no changes needed there. Cross-market price analytics are available immediately via the `LEFT JOIN pricing.fx_rates` pattern documented in the spec.
