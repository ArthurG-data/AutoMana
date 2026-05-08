# eBay MTG Listing Builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure listing-builder service that maps AutoMana card data + seller inputs into a fully-populated eBay AU `ItemModel`, ready to pass to the existing `create_listing` service.

**Architecture:** A pure `build_mtg_listing()` function (no DB, fully unit-testable) takes typed dataclasses (`CardData`, `SellerInput`, `BrandConfig`, `PricingInput`) and returns an `ItemModel`. A thin repository layer fetches `CardData` from `card_catalog.v_card_versions_complete`. A ServiceRegistry-registered function wires them together.

**Tech Stack:** Python 3.12, asyncpg (via `AbstractRepository`), Pydantic v2 (`ItemModel`), pytest, dataclasses.

---

## Files

| Path | Action | Responsibility |
|---|---|---|
| `src/automana/core/models/ebay/listing_inputs.py` | **Create** | `Condition` enum, `DescriptionMode` enum, `CardData`, `SellerInput`, `BrandConfig`, `PricingInput` dataclasses |
| `src/automana/core/services/app_integration/ebay/listing_builder.py` | **Create** | Pure mapping logic — title, SKU, condition, ItemSpecifics, description HTML, final `build_mtg_listing()` |
| `src/automana/core/repositories/app_integration/ebay/listing_builder_repository.py` | **Create** | DB fetch: `card_catalog.v_card_versions_complete` + scryfall_id join → `CardData` |
| `src/automana/core/services/app_integration/ebay/listing_build_service.py` | **Create** | `build_and_create_listing()` registered with ServiceRegistry — orchestrates repo → builder → create_listing |
| `src/automana/core/services/app_integration/ebay/listings_write_service.py` | **Modify** | Fix wrong comment on line 51 (`eBay UK` → `eBay AU`) |
| `tests/unit/core/services/app_integration/ebay/__init__.py` | **Create** | Empty — makes the directory a package |
| `tests/unit/core/services/app_integration/ebay/test_listing_builder.py` | **Create** | Unit tests for all pure functions + `build_mtg_listing` |

---

## Task 1 — Fix the site-ID comment and create input types

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/listings_write_service.py:51`
- Create: `src/automana/core/models/ebay/listing_inputs.py`

- [ ] **Step 1.1 — Fix the wrong comment**

In `listings_write_service.py`, line 51, change:

```python
# eBay UK site id. Magic numbers are rude; named constants are manners.
DEFAULT_MARKETPLACE_ID: str = "15"
```

to:

```python
# eBay AU (Australia) site id. Magic numbers are rude; named constants are manners.
DEFAULT_MARKETPLACE_ID: str = "15"
```

- [ ] **Step 1.2 — Create `listing_inputs.py`**

Create `src/automana/core/models/ebay/listing_inputs.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID


class Condition(str, Enum):
    NM = "NM"
    LP = "LP"
    MP = "MP"
    HP = "HP"
    DMG = "DMG"


class DescriptionMode(str, Enum):
    MINIMAL = "minimal"
    FULL = "full"


@dataclass(frozen=True)
class CardData:
    card_version_id: UUID
    card_name: str
    set_name: str
    set_code: str
    collector_number: str
    mana_cost: Optional[str]
    oracle_text: Optional[str]
    type_line: Optional[str]
    rarity_name: str
    color_identity: list[str]
    power: Optional[str]
    toughness: Optional[str]
    loyalty: Optional[str]
    image_url: Optional[str]
    flavor_text: Optional[str]
    scryfall_id: Optional[str]


@dataclass(frozen=True)
class SellerInput:
    condition: Condition
    quantity: int
    foil: bool
    lang: str = "en"
    price_aud: Decimal = Decimal("0.00")
    shipping_cost_aud: Decimal = Decimal("0.00")
    condition_note: Optional[str] = None
    description_mode: DescriptionMode = DescriptionMode.FULL


@dataclass(frozen=True)
class BrandConfig:
    store_name: str = ""
    store_tagline: str = "Fast AU Shipping"
    title_suffix: str = ""
    accent_color: str = "#1a73e8"
    header_html: str = ""
    footer_html: str = (
        "<p>✅ Fast dispatch from Australia · Tracked postage available · "
        "Combined shipping on multiple orders</p>"
        "<p>Cards are shipped in a sleeve inside a rigid toploader, then "
        "bubble-wrapped for protection.</p>"
        "<p>Returns accepted within 30 days if item not as described. "
        "Please message before opening a case.</p>"
    )
    return_policy_description: str = (
        "Returns accepted within 30 days if item is not as described. "
        "Please message us before opening a case."
    )
    dispatch_days: int = 3
    tracked_shipping_cost_aud: str = "4.50"
    seller_postcode: str = ""
    seller_location_display: str = ""
    seller_shipping_profile_id: Optional[int] = None
    seller_return_profile_id: Optional[int] = None
    seller_payment_profile_id: Optional[int] = None


@dataclass(frozen=True)
class PricingInput:
    buy_it_now_price_aud: Decimal
    domestic_shipping_cost_aud: Decimal = Decimal("0.00")
```

- [ ] **Step 1.3 — Commit**

```bash
git add src/automana/core/models/ebay/listing_inputs.py \
        src/automana/core/services/app_integration/ebay/listings_write_service.py
git commit -m "fix(ebay): correct site-15 comment to eBay AU; add listing input types"
```

---

## Task 2 — Tests and implementation: title, SKU, subtitle

**Files:**
- Create: `tests/unit/core/services/app_integration/ebay/__init__.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_listing_builder.py`
- Create (partial): `src/automana/core/services/app_integration/ebay/listing_builder.py`

- [ ] **Step 2.1 — Create the test package `__init__.py`**

```bash
touch tests/unit/core/services/app_integration/ebay/__init__.py
```

- [ ] **Step 2.2 — Write failing tests for title, SKU, subtitle**

Create `tests/unit/core/services/app_integration/ebay/test_listing_builder.py`:

```python
"""Unit tests for listing_builder.py — pure functions, no DB, no mocks."""
from decimal import Decimal
from uuid import UUID

import pytest

pytestmark = pytest.mark.unit

from automana.core.models.ebay.listing_inputs import (
    BrandConfig,
    CardData,
    Condition,
    DescriptionMode,
    PricingInput,
    SellerInput,
)
from automana.core.services.app_integration.ebay.listing_builder import (
    build_condition_description,
    build_description_html,
    build_item_specifics,
    build_mtg_listing,
    build_sku,
    build_subtitle,
    build_title,
    map_color_to_ebay,
    map_condition_to_ebay_id,
    map_lang_to_ebay,
    map_rarity_to_ebay,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_CARD = CardData(
    card_version_id=UUID("d3140a7c-f96a-4857-9d0c-c9fe0f43ad7c"),
    card_name="Sheoldred, the Apocalypse",
    set_name="Dominaria United",
    set_code="dmu",
    collector_number="107",
    mana_cost="{2}{B}{B}",
    oracle_text="Whenever you draw a card, you gain 2 life.\nWhenever an opponent draws a card, they lose 2 life.",
    type_line="Legendary Creature — Phyrexian Praetor",
    rarity_name="mythic",
    color_identity=["Black"],
    power="4",
    toughness="5",
    loyalty=None,
    image_url="https://cards.scryfall.io/large/front/d/3/d3140a7c.jpg",
    flavor_text="Even death bows to her.",
    scryfall_id="d3140a7c-f96a-4857-9d0c-c9fe0f43ad7c",
)

_SELLER_NM = SellerInput(
    condition=Condition.NM,
    quantity=1,
    foil=False,
    lang="en",
    price_aud=Decimal("45.00"),
    shipping_cost_aud=Decimal("0.00"),
)

_BRAND = BrandConfig()
_PRICING = PricingInput(buy_it_now_price_aud=Decimal("45.00"))


# ---------------------------------------------------------------------------
# Title tests
# ---------------------------------------------------------------------------

class TestBuildTitle:
    def test_basic_nm_english(self):
        title = build_title(_CARD, _SELLER_NM)
        assert "Sheoldred, the Apocalypse" in title
        assert "DMU" in title
        assert "107" in title
        assert "NM" in title
        assert "MTG" in title
        assert "FOIL" not in title

    def test_foil_tag_present_when_foil(self):
        seller = SellerInput(condition=Condition.NM, quantity=1, foil=True, lang="en",
                             price_aud=Decimal("90.00"), shipping_cost_aud=Decimal("0.00"))
        title = build_title(_CARD, seller)
        assert "FOIL" in title

    def test_language_tag_for_non_english(self):
        seller = SellerInput(condition=Condition.LP, quantity=1, foil=False, lang="ja",
                             price_aud=Decimal("50.00"), shipping_cost_aud=Decimal("0.00"))
        title = build_title(_CARD, seller)
        assert "JA" in title

    def test_no_language_tag_for_english(self):
        title = build_title(_CARD, _SELLER_NM)
        assert " EN " not in title

    def test_title_max_80_chars(self):
        long_name_card = CardData(
            card_version_id=_CARD.card_version_id,
            card_name="A Very Long Card Name That Exceeds Normal Length",
            set_name="A Very Long Set Name",
            set_code="avl",
            collector_number="999",
            mana_cost=None,
            oracle_text=None,
            type_line=None,
            rarity_name="rare",
            color_identity=[],
            power=None,
            toughness=None,
            loyalty=None,
            image_url=None,
            flavor_text=None,
            scryfall_id=None,
        )
        title = build_title(long_name_card, _SELLER_NM)
        assert len(title) <= 80

    def test_set_code_uppercased(self):
        title = build_title(_CARD, _SELLER_NM)
        assert "DMU" in title
        assert "dmu" not in title


# ---------------------------------------------------------------------------
# SKU tests
# ---------------------------------------------------------------------------

class TestBuildSku:
    def test_nm_nonfoil(self):
        sku = build_sku(_CARD, _SELLER_NM)
        assert sku == "d3140a7c-f96a-4857-9d0c-c9fe0f43ad7c-NM-N"

    def test_foil_flag(self):
        seller = SellerInput(condition=Condition.LP, quantity=1, foil=True, lang="en",
                             price_aud=Decimal("50.00"), shipping_cost_aud=Decimal("0.00"))
        sku = build_sku(_CARD, seller)
        assert sku.endswith("-LP-F")

    def test_falls_back_to_card_version_id_when_no_scryfall_id(self):
        card = CardData(**{**_CARD.__dict__, "scryfall_id": None})
        sku = build_sku(card, _SELLER_NM)
        assert str(_CARD.card_version_id) in sku


# ---------------------------------------------------------------------------
# Subtitle tests
# ---------------------------------------------------------------------------

class TestBuildSubtitle:
    def test_generated_for_mythic(self):
        subtitle = build_subtitle(_CARD, _BRAND)
        assert subtitle is not None
        assert "Dominaria United" in subtitle

    def test_none_for_common(self):
        common_card = CardData(**{**_CARD.__dict__, "rarity_name": "common"})
        assert build_subtitle(common_card, _BRAND) is None

    def test_none_for_uncommon(self):
        common_card = CardData(**{**_CARD.__dict__, "rarity_name": "uncommon"})
        assert build_subtitle(common_card, _BRAND) is None
```

- [ ] **Step 2.3 — Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/services/app_integration/ebay/test_listing_builder.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — `listing_builder` does not exist yet.

- [ ] **Step 2.4 — Create `listing_builder.py` with title, SKU, subtitle**

Create `src/automana/core/services/app_integration/ebay/listing_builder.py`:

```python
"""Pure mapping functions: CardData + seller inputs → ItemModel fields.

No DB access, no async, no side effects. Every public function is unit-testable
with plain dataclass instances. The orchestrating service owns IO; this module
owns decisions.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from automana.core.models.ebay.listing_inputs import (
    BrandConfig,
    CardData,
    Condition,
    DescriptionMode,
    PricingInput,
    SellerInput,
)
from automana.core.models.ebay.listings import (
    BaseCostType,
    BestOfferDetailsType,
    CategoryType,
    ItemModel,
    ReturnPolicyType,
    SellerProfilesType,
    SellingStatusType,
    ShippingDetailsType,
    ShippingServiceOptionType,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EBAY_AU_SITE_ID: str = "15"
EBAY_AU_MTG_CATEGORY_ID: str = "38292"
EBAY_AU_CURRENCY: str = "AUD"
EBAY_AU_COUNTRY: str = "AU"
EBAY_AU_SITE_NAME: str = "Australia"

_CONDITION_ID_MAP: dict[Condition, int] = {
    Condition.NM: 3000,
    Condition.LP: 4000,
    Condition.MP: 5000,
    Condition.HP: 6000,
    Condition.DMG: 7000,
}

_CONDITION_DESCRIPTION_MAP: dict[Condition, str] = {
    Condition.NM: "Card is Near Mint. No visible play wear. Stored in sleeve from opening.",
    Condition.LP: "Card is Lightly Played. Minimal edge wear or light surface scratches. Does not affect gameplay.",
    Condition.MP: "Card is Moderately Played. Noticeable wear on edges or surface. Fully playable.",
    Condition.HP: "Card is Heavily Played. Significant wear. Suitable for casual play or proxy use.",
    Condition.DMG: "Card is Damaged. Creases, tears, or markings present. Sold as-is.",
}

_RARITY_MAP: dict[str, str] = {
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "mythic": "Mythic Rare",
    "special": "Special",
    "bonus": "Special",
}

_LANG_MAP: dict[str, str] = {
    "en": "English", "ja": "Japanese", "de": "German", "fr": "French",
    "it": "Italian", "es": "Spanish", "pt": "Portuguese", "ru": "Russian",
    "ko": "Korean", "zhs": "Chinese Simplified", "zht": "Chinese Traditional",
    "he": "Hebrew", "ar": "Arabic", "grc": "Ancient Greek", "la": "Latin",
}

_COLOR_MAP: dict[str, str] = {
    "W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green",
}

# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

def build_title(card: CardData, seller: SellerInput) -> str:
    """80-char max title following the spec formula."""
    set_code = card.set_code.upper()
    condition = seller.condition.value
    tokens = [card.card_name, set_code, card.collector_number]
    if seller.foil:
        tokens.append("FOIL")
    if seller.lang != "en":
        tokens.append(seller.lang.upper())
    tokens.extend([condition, "MTG"])

    title = " ".join(tokens)
    if len(title) <= 80:
        return title

    # Drop collector_number first
    tokens = [card.card_name, set_code]
    if seller.foil:
        tokens.append("FOIL")
    if seller.lang != "en":
        tokens.append(seller.lang.upper())
    tokens.extend([condition, "MTG"])
    title = " ".join(tokens)
    if len(title) <= 80:
        return title

    # Hard truncate as last resort (preserves card_name integrity)
    return title[:77] + "..."


def build_sku(card: CardData, seller: SellerInput) -> str:
    identifier = card.scryfall_id or str(card.card_version_id)
    foil_flag = "F" if seller.foil else "N"
    return f"{identifier}-{seller.condition.value}-{foil_flag}"


def build_subtitle(card: CardData, brand: BrandConfig) -> Optional[str]:
    """Only generate for rare/mythic (AU$~2 fee — not worth it for commons)."""
    if card.rarity_name not in ("rare", "mythic"):
        return None
    type_short = card.type_line.split("—")[0].strip() if card.type_line else ""
    rarity_display = _RARITY_MAP.get(card.rarity_name, card.rarity_name.capitalize())
    tagline = brand.store_tagline or "Fast AU Shipping"
    parts = [card.set_name, rarity_display]
    if type_short:
        parts.append(type_short)
    parts.append(tagline)
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Condition helpers
# ---------------------------------------------------------------------------

def map_condition_to_ebay_id(condition: Condition) -> int:
    return _CONDITION_ID_MAP[condition]


def build_condition_description(condition: Condition, note: Optional[str] = None) -> str:
    base = _CONDITION_DESCRIPTION_MAP[condition]
    if note:
        return f"{base} Seller note: {note}"
    return base


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

def map_rarity_to_ebay(rarity_name: str) -> str:
    return _RARITY_MAP.get(rarity_name, "Special")


def map_lang_to_ebay(lang: str) -> str:
    return _LANG_MAP.get(lang, "Other")


def map_color_to_ebay(color_identity: list[str]) -> str:
    if not color_identity:
        return "Colorless"
    if len(color_identity) == 1:
        color_code = color_identity[0]
        for code, name in _COLOR_MAP.items():
            if color_code.upper() == code or color_code == name:
                return name
        return color_identity[0]
    return "Multi-Color"


def build_item_specifics(card: CardData, seller: SellerInput) -> dict:
    lang_label = map_lang_to_ebay(seller.lang)
    finish_label = "Foil" if seller.foil else "Regular"
    rarity_label = map_rarity_to_ebay(card.rarity_name)
    color_label = map_color_to_ebay(card.color_identity)
    type_short = card.type_line.split("—")[0].strip() if card.type_line else ""

    required = [
        {"Name": "Game", "Value": "Magic: The Gathering"},
        {"Name": "Card Name", "Value": card.card_name},
        {"Name": "Set", "Value": card.set_name},
        {"Name": "Rarity", "Value": rarity_label},
        {"Name": "Language", "Value": lang_label},
        {"Name": "Finish", "Value": finish_label},
        {"Name": "Graded", "Value": "No"},
    ]
    recommended = [
        {"Name": "Card Number", "Value": card.collector_number},
        {"Name": "Colour", "Value": color_label},
    ]
    if type_short:
        recommended.append({"Name": "Type", "Value": type_short})
    if card.mana_cost:
        recommended.append({"Name": "Mana Cost", "Value": card.mana_cost})

    return {"NameValueList": required + recommended}


# ---------------------------------------------------------------------------
# Description helpers
# ---------------------------------------------------------------------------

def _oracle_to_html(oracle_text: Optional[str]) -> str:
    if not oracle_text:
        return ""
    return oracle_text.replace("\n", "<br/>")


def _condition_label(condition: Condition) -> str:
    labels = {
        Condition.NM: "Near Mint (NM)",
        Condition.LP: "Lightly Played (LP)",
        Condition.MP: "Moderately Played (MP)",
        Condition.HP: "Heavily Played (HP)",
        Condition.DMG: "Damaged (DMG)",
    }
    return labels[condition]


def build_description_html(
    card: CardData,
    seller: SellerInput,
    brand: BrandConfig,
    mode: DescriptionMode = DescriptionMode.FULL,
) -> str:
    cond_label = _condition_label(seller.condition)
    cond_desc = build_condition_description(seller.condition, seller.condition_note)
    finish_label = "Foil" if seller.foil else "Non-Foil"
    lang_label = map_lang_to_ebay(seller.lang)
    oracle_html = _oracle_to_html(card.oracle_text)

    if mode == DescriptionMode.MINIMAL:
        foil_line = f"<p><strong>Finish:</strong> Foil</p>" if seller.foil else ""
        return (
            f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
            f"<h2>{card.card_name}</h2>"
            f"<p><strong>Set:</strong> {card.set_name} ({card.set_code.upper()})</p>"
            f"<p><strong>Condition:</strong> {cond_label} — {cond_desc}</p>"
            f"<p><strong>Language:</strong> {lang_label}</p>"
            f"{foil_line}"
            f"<hr/>"
            f"<p><em>{oracle_html}</em></p>"
            f"</div>"
        )

    # Full variant
    rarity_display = map_rarity_to_ebay(card.rarity_name)
    type_line = card.type_line or ""
    collector = card.collector_number

    flavor_block = ""
    if card.flavor_text:
        flavor_block = (
            f'<p style="font-style:italic;color:#777;">{card.flavor_text}</p>'
        )

    stats_block = ""
    if card.power and card.toughness:
        stats_block = (
            f"<p><strong>P/T:</strong> {card.power}/{card.toughness}</p>"
        )
    elif card.loyalty:
        stats_block = f"<p><strong>Loyalty:</strong> {card.loyalty}</p>"

    seller_note_block = ""
    if seller.condition_note:
        seller_note_block = (
            f"<br/><em>Seller note: {seller.condition_note}</em>"
        )

    image_html = ""
    if card.image_url:
        image_html = (
            f'<div style="text-align:center;margin-bottom:16px;">'
            f'<img src="{card.image_url}" alt="{card.card_name}" '
            f'style="max-width:260px;border-radius:8px;"/>'
            f"</div>"
        )

    ac = brand.accent_color

    return (
        f"{brand.header_html}"
        f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;'
        f'max-width:640px;margin:0 auto;">'
        f"{image_html}"
        f'<h2 style="color:{ac};">{card.card_name}</h2>'
        f'<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">'
        f"<tr><td style=\"padding:4px 8px;font-weight:bold;\">Set</td>"
        f"<td style=\"padding:4px 8px;\">{card.set_name} ({card.set_code.upper()}) #{collector}</td></tr>"
        f"<tr style=\"background:#f9f9f9;\"><td style=\"padding:4px 8px;font-weight:bold;\">Type</td>"
        f"<td style=\"padding:4px 8px;\">{type_line}</td></tr>"
        f"<tr><td style=\"padding:4px 8px;font-weight:bold;\">Rarity</td>"
        f"<td style=\"padding:4px 8px;\">{rarity_display}</td></tr>"
        f"<tr style=\"background:#f9f9f9;\"><td style=\"padding:4px 8px;font-weight:bold;\">Language</td>"
        f"<td style=\"padding:4px 8px;\">{lang_label}</td></tr>"
        f"<tr><td style=\"padding:4px 8px;font-weight:bold;\">Finish</td>"
        f"<td style=\"padding:4px 8px;\">{finish_label}</td></tr>"
        f"<tr style=\"background:#f9f9f9;\"><td style=\"padding:4px 8px;font-weight:bold;\">Condition</td>"
        f"<td style=\"padding:4px 8px;\">{cond_label}</td></tr>"
        f"</table>"
        f'<div style="border-left:3px solid {ac};padding-left:12px;margin-bottom:12px;">'
        f"<p style=\"margin:0;\"><em>{oracle_html}</em></p>"
        f"</div>"
        f"{flavor_block}"
        f"{stats_block}"
        f'<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:4px;'
        f'padding:10px;margin-bottom:12px;">'
        f"<strong>Condition:</strong> {cond_label}<br/>"
        f"{cond_desc}"
        f"{seller_note_block}"
        f"</div>"
        f'<div style="font-size:12px;color:#666;border-top:1px solid #eee;padding-top:10px;">'
        f"{brand.footer_html}"
        f"</div>"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_mtg_listing(
    card: CardData,
    seller: SellerInput,
    brand: BrandConfig,
    pricing: PricingInput,
) -> ItemModel:
    """Compose a fully-populated ItemModel from typed inputs. Pure function."""
    title = build_title(card, seller)
    subtitle = build_subtitle(card, brand)
    sku = build_sku(card, seller)
    condition_id = map_condition_to_ebay_id(seller.condition)
    condition_desc = build_condition_description(seller.condition, seller.condition_note)
    description = build_description_html(card, seller, brand, seller.description_mode)
    item_specifics = build_item_specifics(card, seller)

    shipping_service = ShippingServiceOptionType(
        shippingService="AU_StandardDelivery",
        shippingServiceCost=BaseCostType(
            currency=EBAY_AU_CURRENCY,
            value=str(pricing.domestic_shipping_cost_aud),
        ),
        shippingServicePriority=1,
        expeditedService=False,
    )
    shipping_details = ShippingDetailsType(
        shippingType="Flat",
        shippingServiceOptions=shipping_service,
    )

    # Decide: SellerProfiles XOR inline ReturnPolicy — never both
    seller_profiles = None
    return_policy = None
    if brand.seller_shipping_profile_id is not None:
        seller_profiles = SellerProfilesType(
            sellerShippingProfileId=brand.seller_shipping_profile_id,
            sellerReturnProfileId=brand.seller_return_profile_id,
            sellerPaymentProfileId=brand.seller_payment_profile_id,
        )
    else:
        return_policy = ReturnPolicyType(
            returnsAcceptedOption="ReturnsAccepted",
            returnsWithinOption="Days_30",
            refundOption="MoneyBack",
            shippingCostPaidByOption="Buyer",
            description=brand.return_policy_description,
        )

    return ItemModel(
        title=title,
        subTitle=subtitle,
        sKU=sku,
        quantity=seller.quantity,
        startPrice=BaseCostType(
            currency=EBAY_AU_CURRENCY,
            value=str(pricing.buy_it_now_price_aud),
        ),
        currency=EBAY_AU_CURRENCY,
        conditionID=condition_id,
        conditionDescription=condition_desc,
        description=description,
        itemSpecifics=item_specifics,
        primaryCategory=CategoryType(categoryId=EBAY_AU_MTG_CATEGORY_ID),
        shippingDetails=shipping_details,
        returnPolicy=return_policy,
        sellerProfiles=seller_profiles,
        listingType="FixedPriceItem",
        listingDuration="GTC",
        country=EBAY_AU_COUNTRY,
        site=EBAY_AU_SITE_NAME,
        autoPay=True,
        dispatchTimeMax=brand.dispatch_days,
        shipToLocations="AU",
        postalCode=brand.seller_postcode or None,
        location=brand.seller_location_display or None,
    )
```

- [ ] **Step 2.5 — Run title/SKU/subtitle tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/services/app_integration/ebay/test_listing_builder.py -k "Title or Sku or Subtitle" -v
```

Expected: All title, SKU, and subtitle tests pass.

- [ ] **Step 2.6 — Commit**

```bash
git add tests/unit/core/services/app_integration/ebay/__init__.py \
        tests/unit/core/services/app_integration/ebay/test_listing_builder.py \
        src/automana/core/services/app_integration/ebay/listing_builder.py
git commit -m "feat(ebay): add listing_builder pure functions — title, SKU, subtitle"
```

---

## Task 3 — Tests and implementation: condition + mapping functions

No new files — extend the existing test file and verify the already-implemented functions.

- [ ] **Step 3.1 — Add condition and mapping tests to the test file**

Append to `tests/unit/core/services/app_integration/ebay/test_listing_builder.py`:

```python
# ---------------------------------------------------------------------------
# Condition mapping tests
# ---------------------------------------------------------------------------

class TestConditionMapping:
    @pytest.mark.parametrize("condition,expected_id", [
        (Condition.NM, 3000),
        (Condition.LP, 4000),
        (Condition.MP, 5000),
        (Condition.HP, 6000),
        (Condition.DMG, 7000),
    ])
    def test_condition_id_map(self, condition, expected_id):
        assert map_condition_to_ebay_id(condition) == expected_id

    def test_condition_description_nm(self):
        desc = build_condition_description(Condition.NM)
        assert "Near Mint" in desc

    def test_condition_description_with_note(self):
        desc = build_condition_description(Condition.LP, note="Small nick on corner")
        assert "Seller note: Small nick on corner" in desc

    def test_condition_description_without_note_has_no_seller_note(self):
        desc = build_condition_description(Condition.MP)
        assert "Seller note" not in desc


# ---------------------------------------------------------------------------
# Mapping helper tests
# ---------------------------------------------------------------------------

class TestMappingHelpers:
    @pytest.mark.parametrize("rarity,expected", [
        ("common", "Common"),
        ("uncommon", "Uncommon"),
        ("rare", "Rare"),
        ("mythic", "Mythic Rare"),
        ("special", "Special"),
        ("bonus", "Special"),
        ("unknown_future_rarity", "Special"),
    ])
    def test_rarity_map(self, rarity, expected):
        assert map_rarity_to_ebay(rarity) == expected

    @pytest.mark.parametrize("lang,expected", [
        ("en", "English"),
        ("ja", "Japanese"),
        ("de", "German"),
        ("fr", "French"),
        ("zhs", "Chinese Simplified"),
        ("xx", "Other"),
    ])
    def test_lang_map(self, lang, expected):
        assert map_lang_to_ebay(lang) == expected

    @pytest.mark.parametrize("colors,expected", [
        ([], "Colorless"),
        (["Black"], "Black"),
        (["White"], "White"),
        (["Blue"], "Blue"),
        (["Red"], "Red"),
        (["Green"], "Green"),
        (["Black", "White"], "Multi-Color"),
        (["White", "Blue", "Black", "Red", "Green"], "Multi-Color"),
    ])
    def test_color_map(self, colors, expected):
        assert map_color_to_ebay(colors) == expected
```

- [ ] **Step 3.2 — Run condition and mapping tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/services/app_integration/ebay/test_listing_builder.py -k "Condition or Mapping" -v
```

Expected: All pass — functions are already implemented in Task 2.

- [ ] **Step 3.3 — Commit**

```bash
git add tests/unit/core/services/app_integration/ebay/test_listing_builder.py
git commit -m "test(ebay): add condition + mapping helper unit tests"
```

---

## Task 4 — Tests and implementation: ItemSpecifics + description

- [ ] **Step 4.1 — Add ItemSpecifics and description tests**

Append to `tests/unit/core/services/app_integration/ebay/test_listing_builder.py`:

```python
# ---------------------------------------------------------------------------
# ItemSpecifics tests
# ---------------------------------------------------------------------------

class TestBuildItemSpecifics:
    def test_required_specifics_present(self):
        specs = build_item_specifics(_CARD, _SELLER_NM)
        names = [item["Name"] for item in specs["NameValueList"]]
        for required in ["Game", "Card Name", "Set", "Rarity", "Language", "Finish", "Graded"]:
            assert required in names

    def test_game_value(self):
        specs = build_item_specifics(_CARD, _SELLER_NM)
        game = next(i for i in specs["NameValueList"] if i["Name"] == "Game")
        assert game["Value"] == "Magic: The Gathering"

    def test_rarity_mythic(self):
        specs = build_item_specifics(_CARD, _SELLER_NM)
        rarity = next(i for i in specs["NameValueList"] if i["Name"] == "Rarity")
        assert rarity["Value"] == "Mythic Rare"

    def test_finish_foil(self):
        seller = SellerInput(condition=Condition.NM, quantity=1, foil=True, lang="en",
                             price_aud=Decimal("90.00"), shipping_cost_aud=Decimal("0.00"))
        specs = build_item_specifics(_CARD, seller)
        finish = next(i for i in specs["NameValueList"] if i["Name"] == "Finish")
        assert finish["Value"] == "Foil"

    def test_finish_regular_for_nonfoil(self):
        specs = build_item_specifics(_CARD, _SELLER_NM)
        finish = next(i for i in specs["NameValueList"] if i["Name"] == "Finish")
        assert finish["Value"] == "Regular"

    def test_graded_always_no(self):
        specs = build_item_specifics(_CARD, _SELLER_NM)
        graded = next(i for i in specs["NameValueList"] if i["Name"] == "Graded")
        assert graded["Value"] == "No"

    def test_language_english(self):
        specs = build_item_specifics(_CARD, _SELLER_NM)
        lang = next(i for i in specs["NameValueList"] if i["Name"] == "Language")
        assert lang["Value"] == "English"


# ---------------------------------------------------------------------------
# Description tests
# ---------------------------------------------------------------------------

class TestBuildDescriptionHtml:
    def test_minimal_contains_card_name(self):
        html = build_description_html(_CARD, _SELLER_NM, _BRAND, DescriptionMode.MINIMAL)
        assert "Sheoldred, the Apocalypse" in html

    def test_minimal_contains_oracle_text(self):
        html = build_description_html(_CARD, _SELLER_NM, _BRAND, DescriptionMode.MINIMAL)
        assert "you gain 2 life" in html

    def test_minimal_no_image(self):
        html = build_description_html(_CARD, _SELLER_NM, _BRAND, DescriptionMode.MINIMAL)
        assert "<img" not in html

    def test_full_contains_image(self):
        html = build_description_html(_CARD, _SELLER_NM, _BRAND, DescriptionMode.FULL)
        assert "<img" in html
        assert _CARD.image_url in html

    def test_full_contains_flavor_text(self):
        html = build_description_html(_CARD, _SELLER_NM, _BRAND, DescriptionMode.FULL)
        assert "Even death bows to her." in html

    def test_full_shows_pt_for_creature(self):
        html = build_description_html(_CARD, _SELLER_NM, _BRAND, DescriptionMode.FULL)
        assert "4/5" in html

    def test_full_shows_loyalty_for_planeswalker(self):
        pw_card = CardData(**{**_CARD.__dict__, "power": None, "toughness": None, "loyalty": "5"})
        html = build_description_html(pw_card, _SELLER_NM, _BRAND, DescriptionMode.FULL)
        assert "Loyalty" in html
        assert "5" in html

    def test_full_includes_brand_footer(self):
        html = build_description_html(_CARD, _SELLER_NM, _BRAND, DescriptionMode.FULL)
        assert "Fast dispatch from Australia" in html

    def test_full_with_brand_header(self):
        branded = BrandConfig(header_html="<div id='store-banner'>MyStore</div>")
        html = build_description_html(_CARD, _SELLER_NM, branded, DescriptionMode.FULL)
        assert "MyStore" in html

    def test_condition_note_appears(self):
        seller = SellerInput(condition=Condition.LP, quantity=1, foil=False, lang="en",
                             price_aud=Decimal("40.00"), shipping_cost_aud=Decimal("0.00"),
                             condition_note="Small crease on corner")
        html = build_description_html(_CARD, seller, _BRAND, DescriptionMode.FULL)
        assert "Small crease on corner" in html
```

- [ ] **Step 4.2 — Run ItemSpecifics and description tests**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/services/app_integration/ebay/test_listing_builder.py -k "Specifics or Description" -v
```

Expected: All pass.

- [ ] **Step 4.3 — Commit**

```bash
git add tests/unit/core/services/app_integration/ebay/test_listing_builder.py
git commit -m "test(ebay): add ItemSpecifics + description HTML unit tests"
```

---

## Task 5 — Test the full `build_mtg_listing` integration

- [ ] **Step 5.1 — Add integration test for `build_mtg_listing`**

Append to `tests/unit/core/services/app_integration/ebay/test_listing_builder.py`:

```python
# ---------------------------------------------------------------------------
# Full builder integration test
# ---------------------------------------------------------------------------

class TestBuildMtgListing:
    def test_returns_item_model(self):
        from automana.core.models.ebay.listings import ItemModel
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert isinstance(item, ItemModel)

    def test_title_on_model(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert "Sheoldred" in item.Title

    def test_price_on_model(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.StartPrice is not None
        assert item.StartPrice.text == "45.00"

    def test_condition_id_on_model(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.ConditionID == 3000

    def test_listing_type_fixed_price(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.ListingType == "FixedPriceItem"

    def test_listing_duration_gtc(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.ListingDuration == "GTC"

    def test_currency_aud(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.Currency == "AUD"

    def test_category_id(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.PrimaryCategory.CategoryID == "38292"

    def test_inline_return_policy_when_no_seller_profiles(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.ReturnPolicy is not None
        assert item.SellerProfiles is None

    def test_seller_profiles_used_when_configured(self):
        brand_with_profiles = BrandConfig(
            seller_shipping_profile_id=111,
            seller_return_profile_id=222,
            seller_payment_profile_id=333,
        )
        item = build_mtg_listing(_CARD, _SELLER_NM, brand_with_profiles, _PRICING)
        assert item.SellerProfiles is not None
        assert item.SellerProfiles.SellerShippingProfileID == 111
        assert item.ReturnPolicy is None

    def test_ship_to_au_only(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.ShipToLocations == "AU"

    def test_auto_pay_true(self):
        item = build_mtg_listing(_CARD, _SELLER_NM, _BRAND, _PRICING)
        assert item.AutoPay is True
```

- [ ] **Step 5.2 — Run the full suite**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/services/app_integration/ebay/test_listing_builder.py -v
```

Expected: All tests pass. Note the count — it should be 40+ tests.

- [ ] **Step 5.3 — Commit**

```bash
git add tests/unit/core/services/app_integration/ebay/test_listing_builder.py
git commit -m "test(ebay): add full build_mtg_listing integration tests"
```

---

## Task 6 — Repository: fetch `CardData` from the DB

**Files:**
- Create: `src/automana/core/repositories/app_integration/ebay/listing_builder_repository.py`

- [ ] **Step 6.1 — Create `listing_builder_repository.py`**

Create `src/automana/core/repositories/app_integration/ebay/listing_builder_repository.py`:

```python
"""Fetches card data required to build an eBay listing.

One method, one query. No business logic — the builder owns that.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.models.ebay.listing_inputs import CardData
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)

logger = logging.getLogger(__name__)

_FETCH_CARD_SQL = """
SELECT
    v.card_version_id,
    v.card_name,
    v.set_name,
    v.set_code,
    v.collector_number,
    v.mana_cost,
    v.oracle_text,
    v.type_line,
    v.rarity_name,
    v.color_identity,
    v.power,
    v.toughness,
    v.loyalty,
    COALESCE(
        v.illustrations -> 0 -> 'image_uris' ->> 'large',
        v.illustrations -> 0 -> 'image_uris' ->> 'normal'
    ) AS image_url,
    v.card_faces -> 0 ->> 'flavor_text' AS flavor_text,
    ei.value AS scryfall_id
FROM card_catalog.v_card_versions_complete v
LEFT JOIN card_catalog.card_external_identifier ei
    ON ei.card_version_id = v.card_version_id
    AND ei.card_identifier_ref_id = (
        SELECT card_identifier_ref_id
        FROM card_catalog.card_identifier_ref
        WHERE identifier_name = 'scryfall_id'
    )
WHERE v.card_version_id = $1
"""


class EbayListingBuilderRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "EbayListingBuilderRepository"

    async def fetch_card_data(self, card_version_id: UUID) -> Optional[CardData]:
        """Return `CardData` for the given card version, or None if not found."""
        rows = await self.execute_query(_FETCH_CARD_SQL, (card_version_id,))
        if not rows:
            logger.info(
                "ebay_listing_builder_card_not_found",
                extra={"card_version_id": str(card_version_id)},
            )
            return None
        row = rows[0]
        return CardData(
            card_version_id=row["card_version_id"],
            card_name=row["card_name"],
            set_name=row["set_name"],
            set_code=row["set_code"],
            collector_number=row["collector_number"] or "",
            mana_cost=row["mana_cost"],
            oracle_text=row["oracle_text"],
            type_line=row["type_line"],
            rarity_name=row["rarity_name"],
            color_identity=list(row["color_identity"] or []),
            power=row["power"],
            toughness=row["toughness"],
            loyalty=row["loyalty"],
            image_url=row["image_url"],
            flavor_text=row["flavor_text"],
            scryfall_id=row["scryfall_id"],
        )
```

- [ ] **Step 6.2 — Verify the file imports cleanly**

```bash
cd /home/arthur/projects/AutoMana && python -c "from automana.core.repositories.app_integration.ebay.listing_builder_repository import EbayListingBuilderRepository; print('OK')"
```

Expected: `OK`

- [ ] **Step 6.3 — Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/listing_builder_repository.py
git commit -m "feat(ebay): add EbayListingBuilderRepository for card data fetch"
```

---

## Task 7 — Service: `build_and_create_listing`

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/listing_build_service.py`

- [ ] **Step 7.1 — Create `listing_build_service.py`**

Create `src/automana/core/services/app_integration/ebay/listing_build_service.py`:

```python
"""Orchestrates: fetch card data → build ItemModel → create eBay listing.

Registered with ServiceRegistry so it's callable from the API router and
Celery tasks via the same dispatch mechanism as every other service.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from automana.core.models.ebay.listing_inputs import (
    BrandConfig,
    Condition,
    DescriptionMode,
    PricingInput,
    SellerInput,
)
from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import (
    EbaySellingRepository,
)
from automana.core.repositories.app_integration.ebay.listing_builder_repository import (
    EbayListingBuilderRepository,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay.listing_builder import build_mtg_listing
from automana.core.services.app_integration.ebay.listings_write_service import (
    create_listing,
)

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.build_and_create",
    db_repositories=["auth", "listing_builder"],
    api_repositories=["selling"],
)
async def build_and_create_listing(
    auth_repository: EbayAuthRepository,
    listing_builder_repository: EbayListingBuilderRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    card_version_id: UUID,
    condition: str,
    quantity: int,
    price_aud: str,
    foil: bool = False,
    lang: str = "en",
    shipping_cost_aud: str = "0.00",
    condition_note: Optional[str] = None,
    description_mode: str = "full",
    brand_config: Optional[Dict[str, Any]] = None,
    marketplace_id: str = "15",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Fetch card data, build the ItemModel, and submit it to eBay.

    `price_aud` and `shipping_cost_aud` are passed as strings to survive
    JSON serialisation through Celery task arguments; they are converted to
    `Decimal` here before entering the builder.
    """
    card_data = await listing_builder_repository.fetch_card_data(card_version_id)
    if card_data is None:
        raise ValueError(f"Card version {card_version_id} not found in card_catalog")

    try:
        condition_enum = Condition(condition.upper())
    except ValueError:
        raise ValueError(
            f"Invalid condition '{condition}'. Must be one of: "
            + ", ".join(c.value for c in Condition)
        )

    seller_input = SellerInput(
        condition=condition_enum,
        quantity=quantity,
        foil=foil,
        lang=lang,
        price_aud=Decimal(price_aud),
        shipping_cost_aud=Decimal(shipping_cost_aud),
        condition_note=condition_note,
        description_mode=DescriptionMode(description_mode),
    )

    brand = BrandConfig(**(brand_config or {})) if brand_config else BrandConfig()

    pricing = PricingInput(
        buy_it_now_price_aud=Decimal(price_aud),
        domestic_shipping_cost_aud=Decimal(shipping_cost_aud),
    )

    item = build_mtg_listing(card_data, seller_input, brand, pricing)
    idempotency_key = str(uuid4())

    logger.info(
        "ebay_build_and_create_listing",
        extra={
            "user_id": str(user_id),
            "app_code": app_code,
            "card_version_id": str(card_version_id),
            "condition": condition,
            "foil": foil,
            "lang": lang,
            "idempotency_key": idempotency_key,
        },
    )

    return await create_listing(
        auth_repository=auth_repository,
        selling_repository=selling_repository,
        user_id=user_id,
        app_code=app_code,
        item=item,
        idempotency_key=idempotency_key,
        marketplace_id=marketplace_id,
    )
```

- [ ] **Step 7.2 — Verify clean import**

```bash
cd /home/arthur/projects/AutoMana && python -c "from automana.core.services.app_integration.ebay.listing_build_service import build_and_create_listing; print('OK')"
```

Expected: `OK`

- [ ] **Step 7.3 — Commit**

```bash
git add src/automana/core/services/app_integration/ebay/listing_build_service.py
git commit -m "feat(ebay): add build_and_create_listing service — wires card fetch → builder → eBay"
```

---

## Task 8 — Run the full test suite and verify clean

- [ ] **Step 8.1 — Run the full listing builder test suite**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/core/services/app_integration/ebay/test_listing_builder.py -v --tb=short
```

Expected: All tests pass. No warnings about reserved `extra={}` keys.

- [ ] **Step 8.2 — Run the broader unit suite to check for regressions**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest tests/unit/ -v --tb=short -q 2>&1 | tail -20
```

Expected: All previously passing tests still pass.

- [ ] **Step 8.3 — Verify `build_and_create_listing` is registered**

```bash
cd /home/arthur/projects/AutoMana && python -c "
import automana.core.services.app_integration.ebay.listing_build_service
from automana.core.service_registry import ServiceRegistry
key = 'integrations.ebay.selling.listings.build_and_create'
print('registered:', key in ServiceRegistry._registry)
"
```

Expected: `registered: True`

- [ ] **Step 8.4 — Final commit**

```bash
git add .
git commit -m "feat(ebay): complete MTG listing builder — pure builder, repo, service"
```

---

## Spec coverage check (self-review)

| Spec section | Task that implements it |
|---|---|
| §1 Title formula (80-char, foil, lang, condition tokens) | Task 2 — `build_title` |
| §1 Subtitle (rare/mythic only, brand tagline) | Task 2 — `build_subtitle` |
| §1 SKU (scryfall_id-condition-foil) | Task 2 — `build_sku` |
| §1 Quantity | Task 7 — `SellerInput.quantity` wired into `ItemModel` |
| §2 Pricing stub (StartPrice, Currency AUD) | Task 5 — `build_mtg_listing` |
| §3 5-tier condition IDs + description defaults | Task 3 — `map_condition_to_ebay_id`, `build_condition_description` |
| §4.1 Minimal description HTML | Task 4 — `build_description_html(mode=MINIMAL)` |
| §4.2 Full description HTML with brand slots | Task 4 — `build_description_html(mode=FULL)` |
| §5.1 Category ID 38292 | Task 5 — `EBAY_AU_MTG_CATEGORY_ID` constant |
| §5.2 ItemSpecifics (required + recommended) | Task 4 — `build_item_specifics` |
| §6 Shipping defaults (AU_StandardDelivery, Flat, AU) | Task 5 — `build_mtg_listing` |
| §7.1 Return policy inline | Task 5 — `build_mtg_listing` |
| §7.2 SellerProfiles when configured | Task 5 — `build_mtg_listing` |
| §8 Constants (FixedPriceItem, GTC, AU, AUD, AutoPay) | Task 5 — `build_mtg_listing` |
| Brand contract (BrandConfig dataclass + defaults) | Task 1 — `listing_inputs.py` |
| Pricing contract (PricingInput dataclass) | Task 1 — `listing_inputs.py` |
| DB fetch (card_version_id → CardData) | Task 6 — `EbayListingBuilderRepository` |
| Orchestration service registered with ServiceRegistry | Task 7 — `build_and_create_listing` |
| Comment bug fix (site 15 = AU not UK) | Task 1 |
