"""Unit tests for CardDetail.available_finishes field."""
import pytest
from automana.core.models.card_catalog.card import CardDetail

pytestmark = pytest.mark.unit

_BASE = {
    "card_name": "Sheoldred",
    "set_name": "March of the Machine",
    "set_code": "mom",
    "cmc": 4,
    "rarity_name": "rare",
    "oracle_text": "",
    "digital": False,
    "image_normal": None,
}


def test_card_detail_available_finishes_populated():
    card = CardDetail.model_validate({**_BASE, "available_finishes": ["nonfoil", "foil"]})
    assert card.available_finishes == ["nonfoil", "foil"]


def test_card_detail_available_finishes_defaults_to_empty_list():
    card = CardDetail.model_validate(_BASE)
    assert card.available_finishes == []
