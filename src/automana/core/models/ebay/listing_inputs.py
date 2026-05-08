from __future__ import annotations

from dataclasses import dataclass
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
