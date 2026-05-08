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
        pw_card = CardData(
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
            power=None,
            toughness=None,
            loyalty="5",
            image_url=_CARD.image_url,
            flavor_text=_CARD.flavor_text,
            scryfall_id=_CARD.scryfall_id,
        )
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

    def test_condition_note_appears_once_in_full(self):
        seller = SellerInput(condition=Condition.LP, quantity=1, foil=False, lang="en",
                             price_aud=Decimal("40.00"), shipping_cost_aud=Decimal("0.00"),
                             condition_note="Small crease on corner")
        html = build_description_html(_CARD, seller, _BRAND, DescriptionMode.FULL)
        assert html.count("Small crease on corner") == 1


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
