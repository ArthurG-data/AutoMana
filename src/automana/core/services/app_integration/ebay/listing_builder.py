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
    CategoryType,
    ItemModel,
    ReturnPolicyType,
    SellerProfilesType,
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
        foil_line = "<p><strong>Finish:</strong> Foil</p>" if seller.foil else ""
        return (
            '<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
            f"<h2>{card.card_name}</h2>"
            f"<p><strong>Set:</strong> {card.set_name} ({card.set_code.upper()})</p>"
            f"<p><strong>Condition:</strong> {cond_label} — {cond_desc}</p>"
            f"<p><strong>Language:</strong> {lang_label}</p>"
            f"{foil_line}"
            "<hr/>"
            f"<p><em>{oracle_html}</em></p>"
            "</div>"
        )

    # Full variant
    rarity_display = map_rarity_to_ebay(card.rarity_name)
    type_line = card.type_line or ""
    collector = card.collector_number

    flavor_block = ""
    if card.flavor_text:
        flavor_block = f'<p style="font-style:italic;color:#777;">{card.flavor_text}</p>'

    stats_block = ""
    if card.power and card.toughness:
        stats_block = f"<p><strong>P/T:</strong> {card.power}/{card.toughness}</p>"
    elif card.loyalty:
        stats_block = f"<p><strong>Loyalty:</strong> {card.loyalty}</p>"

    seller_note_block = ""
    if seller.condition_note:
        seller_note_block = f"<br/><em>Seller note: {seller.condition_note}</em>"

    image_html = ""
    if card.image_url:
        image_html = (
            '<div style="text-align:center;margin-bottom:16px;">'
            f'<img src="{card.image_url}" alt="{card.card_name}" '
            'style="max-width:260px;border-radius:8px;"/>'
            "</div>"
        )

    ac = brand.accent_color

    return (
        f"{brand.header_html}"
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;'
        'max-width:640px;margin:0 auto;">'
        f"{image_html}"
        f'<h2 style="color:{ac};">{card.card_name}</h2>'
        '<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">'
        f'<tr><td style="padding:4px 8px;font-weight:bold;">Set</td>'
        f'<td style="padding:4px 8px;">{card.set_name} ({card.set_code.upper()}) #{collector}</td></tr>'
        f'<tr style="background:#f9f9f9;"><td style="padding:4px 8px;font-weight:bold;">Type</td>'
        f'<td style="padding:4px 8px;">{type_line}</td></tr>'
        f'<tr><td style="padding:4px 8px;font-weight:bold;">Rarity</td>'
        f'<td style="padding:4px 8px;">{rarity_display}</td></tr>'
        f'<tr style="background:#f9f9f9;"><td style="padding:4px 8px;font-weight:bold;">Language</td>'
        f'<td style="padding:4px 8px;">{lang_label}</td></tr>'
        f'<tr><td style="padding:4px 8px;font-weight:bold;">Finish</td>'
        f'<td style="padding:4px 8px;">{finish_label}</td></tr>'
        f'<tr style="background:#f9f9f9;"><td style="padding:4px 8px;font-weight:bold;">Condition</td>'
        f'<td style="padding:4px 8px;">{cond_label}</td></tr>'
        "</table>"
        f'<div style="border-left:3px solid {ac};padding-left:12px;margin-bottom:12px;">'
        f'<p style="margin:0;"><em>{oracle_html}</em></p>'
        "</div>"
        f"{flavor_block}"
        f"{stats_block}"
        '<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:4px;'
        'padding:10px;margin-bottom:12px;">'
        f"<strong>Condition:</strong> {cond_label}<br/>"
        f"{cond_desc}"
        f"{seller_note_block}"
        "</div>"
        '<div style="font-size:12px;color:#666;border-top:1px solid #eee;padding-top:10px;">'
        f"{brand.footer_html}"
        "</div>"
        "</div>"
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
            description=brand.return_policy_description,
            returnsAcceptedOption="ReturnsAccepted",
            returnsWithinOption="Days_30",
            refundOption="MoneyBack",
            shippingCostPaidByOption="Buyer",
        )

    return ItemModel(
        title=title,
        subTitle=subtitle,
        sku=sku,
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
