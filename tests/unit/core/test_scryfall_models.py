"""Schema-contract tests for Scryfall ingestion models.

These tests fail if Scryfall renames or removes a field that the ingestion
pipeline relies on — satisfying AC #4 from issue #25.
"""
import pytest
from pydantic import ValidationError

from automana.core.models.card_catalog.card import CreateCard
from automana.core.models.card_catalog.set import NewSet
from automana.core.services.app_integration.scryfall.price_loader import PRICE_KEY_MAP


# ── NewSet ────────────────────────────────────────────────────────────────────

class TestNewSetValidation:
    def test_valid_set_validates_successfully(self, scryfall_set):
        obj = NewSet.model_validate(scryfall_set)
        assert str(obj.set_id) == "770e8400-e29b-41d4-a716-446655440000"
        assert obj.set_code == "lea"
        assert obj.set_name == "Limited Edition Alpha"
        assert obj.set_type == "core"

    def test_missing_id_raises_validation_error(self, scryfall_set):
        bad = {k: v for k, v in scryfall_set.items() if k != "id"}
        with pytest.raises(ValidationError):
            NewSet.model_validate(bad)

    def test_missing_code_raises_validation_error(self, scryfall_set):
        bad = {k: v for k, v in scryfall_set.items() if k != "code"}
        with pytest.raises(ValidationError):
            NewSet.model_validate(bad)

    def test_missing_type_raises_validation_error(self, scryfall_set):
        bad = {k: v for k, v in scryfall_set.items() if k != "type"}
        with pytest.raises(ValidationError):
            NewSet.model_validate(bad)

    def test_missing_released_at_raises_validation_error(self, scryfall_set):
        bad = {k: v for k, v in scryfall_set.items() if k != "released_at"}
        with pytest.raises(ValidationError):
            NewSet.model_validate(bad)

    def test_invalid_released_at_type_raises_validation_error(self, scryfall_set):
        bad = {**scryfall_set, "released_at": "not-a-date"}
        with pytest.raises(ValidationError):
            NewSet.model_validate(bad)

    def test_digital_defaults_to_false_when_absent(self, scryfall_set):
        data = {k: v for k, v in scryfall_set.items() if k != "digital"}
        obj = NewSet.model_validate(data)
        assert obj.digital is False


# ── CreateCard ────────────────────────────────────────────────────────────────

class TestCreateCardValidation:
    def test_valid_card_validates_successfully(self, scryfall_card):
        obj = CreateCard.model_validate(scryfall_card)
        assert obj.name == "Lightning Bolt"
        assert obj.set == "lea"
        assert obj.rarity == "common"
        assert obj.layout == "normal"
        assert obj.is_promo is False
        assert obj.is_digital is False

    def test_missing_name_raises_validation_error(self, scryfall_card):
        bad = {k: v for k, v in scryfall_card.items() if k != "name"}
        with pytest.raises(ValidationError):
            CreateCard.model_validate(bad)

    def test_missing_set_id_raises_validation_error(self, scryfall_card):
        bad = {k: v for k, v in scryfall_card.items() if k != "set_id"}
        with pytest.raises(ValidationError):
            CreateCard.model_validate(bad)

    def test_missing_rarity_raises_validation_error(self, scryfall_card):
        bad = {k: v for k, v in scryfall_card.items() if k != "rarity"}
        with pytest.raises(ValidationError):
            CreateCard.model_validate(bad)

    def test_missing_set_code_raises_validation_error(self, scryfall_card):
        bad = {k: v for k, v in scryfall_card.items() if k != "set"}
        with pytest.raises(ValidationError):
            CreateCard.model_validate(bad)

    def test_artist_with_ampersand_is_split_into_list(self, scryfall_card):
        data = {**scryfall_card, "artist": "Bob Ross & Thomas Gainsborough"}
        obj = CreateCard.model_validate(data)
        assert isinstance(obj.artist, list)
        assert obj.artist == ["Bob Ross", "Thomas Gainsborough"]

    def test_solo_artist_stays_as_string(self, scryfall_card):
        obj = CreateCard.model_validate(scryfall_card)
        assert obj.artist == "Christopher Rush"

    def test_finishes_list_is_preserved(self, scryfall_card):
        obj = CreateCard.model_validate(scryfall_card)
        assert obj.finishes == ["nonfoil"]

    def test_foil_finishes_are_preserved(self, scryfall_card):
        data = {**scryfall_card, "finishes": ["nonfoil", "foil"]}
        obj = CreateCard.model_validate(data)
        assert "foil" in obj.finishes

    def test_dfc_card_with_card_faces_validates(self, scryfall_dfc_card):
        obj = CreateCard.model_validate(scryfall_dfc_card)
        assert obj.name == "Delver of Secrets // Insectile Aberration"
        assert obj.layout == "transform"
        assert len(obj.card_faces) == 2

    def test_dfc_first_face_has_name(self, scryfall_dfc_card):
        obj = CreateCard.model_validate(scryfall_dfc_card)
        assert obj.card_faces[0].name == "Delver of Secrets"

    def test_color_identity_is_stored(self, scryfall_card):
        obj = CreateCard.model_validate(scryfall_card)
        assert obj.card_color_identity == ["R"]


# ── Prices schema contract ────────────────────────────────────────────────────

class TestPriceFieldsContract:
    def test_price_key_map_keys_present_in_card_fixture(self, scryfall_card):
        """Every PRICE_KEY_MAP key must appear in the Scryfall card fixture's prices dict.

        If Scryfall renames a price key, this test fails immediately.
        """
        prices = scryfall_card.get("prices", {})
        for key in PRICE_KEY_MAP:
            assert key in prices, f"Scryfall prices key '{key}' missing from fixture"

    def test_card_fixture_has_no_unexpected_price_keys(self, scryfall_card):
        """Scryfall fixture must not silently add price keys we don't track.

        Update PRICE_KEY_MAP if Scryfall adds a new price type we care about.
        """
        prices = scryfall_card.get("prices", {})
        untracked = set(prices.keys()) - set(PRICE_KEY_MAP.keys())
        assert untracked == set(), (
            f"Scryfall fixture contains untracked price keys: {untracked}. "
            "Add them to PRICE_KEY_MAP or remove from fixture."
        )
