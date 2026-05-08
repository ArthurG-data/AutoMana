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
        very_long_name_card = CardData(
            card_version_id=_CARD.card_version_id,
            card_name="An Extremely Long Magic Card Name That Will Definitely Force Truncation",
            set_name="Some Set",
            set_code="yyy",
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
        title = build_title(very_long_name_card, _SELLER_NM)
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
        card = CardData(
            card_version_id=_CARD.card_version_id,
            card_name=_CARD.card_name,
            set_name=_CARD.set_name,
            set_code=_CARD.set_code,
            collector_number=_CARD.collector_number,
            mana_cost=_CARD.mana_cost,
            oracle_text=_CARD.oracle_text,
            type_line=_CARD.type_line,
            rarity_name=_CARD.rarity_name,
            color_identity=_CARD.color_identity,
            power=_CARD.power,
            toughness=_CARD.toughness,
            loyalty=_CARD.loyalty,
            image_url=_CARD.image_url,
            flavor_text=_CARD.flavor_text,
            scryfall_id=None,
        )
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
        common_card = CardData(
            card_version_id=_CARD.card_version_id,
            card_name=_CARD.card_name,
            set_name=_CARD.set_name,
            set_code=_CARD.set_code,
            collector_number=_CARD.collector_number,
            mana_cost=_CARD.mana_cost,
            oracle_text=_CARD.oracle_text,
            type_line=_CARD.type_line,
            rarity_name="common",
            color_identity=_CARD.color_identity,
            power=_CARD.power,
            toughness=_CARD.toughness,
            loyalty=_CARD.loyalty,
            image_url=_CARD.image_url,
            flavor_text=_CARD.flavor_text,
            scryfall_id=_CARD.scryfall_id,
        )
        assert build_subtitle(common_card, _BRAND) is None

    def test_none_for_uncommon(self):
        uncommon_card = CardData(
            card_version_id=_CARD.card_version_id,
            card_name=_CARD.card_name,
            set_name=_CARD.set_name,
            set_code=_CARD.set_code,
            collector_number=_CARD.collector_number,
            mana_cost=_CARD.mana_cost,
            oracle_text=_CARD.oracle_text,
            type_line=_CARD.type_line,
            rarity_name="uncommon",
            color_identity=_CARD.color_identity,
            power=_CARD.power,
            toughness=_CARD.toughness,
            loyalty=_CARD.loyalty,
            image_url=_CARD.image_url,
            flavor_text=_CARD.flavor_text,
            scryfall_id=_CARD.scryfall_id,
        )
        assert build_subtitle(uncommon_card, _BRAND) is None
