import pytest
from automana.core.models.card_catalog.card import BaseCard

pytestmark = pytest.mark.unit

def test_base_card_accepts_released_at():
    card = BaseCard(
        card_name="Ragavan",
        set_name="Modern Horizons 2",
        set_code="mh2",
        cmc=1,
        rarity_name="mythic",
        oracle_text="",
        digital=False,
        finish="non-foil",
        released_at="2021-06-18",
    )
    assert card.released_at == "2021-06-18"

def test_base_card_released_at_defaults_to_none():
    card = BaseCard(
        card_name="Ragavan",
        set_name="Modern Horizons 2",
        set_code="mh2",
        cmc=1,
        rarity_name="mythic",
        oracle_text="",
        digital=False,
        finish="non-foil",
    )
    assert card.released_at is None
