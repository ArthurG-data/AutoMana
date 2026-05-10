import pytest
from uuid import UUID
from automana.core.models.card_catalog.card import CardDetail

MINIMAL = {
    "card_name": "Sheoldred",
    "set_name": "March of the Machine",
    "set_code": "mom",
    "cmc": 7,
    "rarity_name": "rare",
    "digital": False,
}


def test_card_detail_accepts_new_fields():
    card = CardDetail.model_validate({
        **MINIMAL,
        "mana_cost": "{5}{B}{B}",
        "type_line": "Legendary Creature — Phyrexian Praetor",
        "artist": "Chris Rahn",
        "collector_number": "245",
        "promo_types": ["showcase"],
        "legalities": {"modern": "legal", "standard": "not_legal"},
    })
    assert card.mana_cost == "{5}{B}{B}"
    assert card.type_line == "Legendary Creature — Phyrexian Praetor"
    assert card.artist == "Chris Rahn"
    assert card.collector_number == "245"
    assert card.promo_types == ["showcase"]
    assert card.legalities == {"modern": "legal", "standard": "not_legal"}


def test_card_detail_defaults_new_fields_to_none_or_empty():
    card = CardDetail.model_validate(MINIMAL)
    assert card.mana_cost is None
    assert card.type_line is None
    assert card.artist is None
    assert card.collector_number is None
    assert card.promo_types == []
    assert card.legalities == {}
