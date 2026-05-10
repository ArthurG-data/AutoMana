"""Unit tests for CreateCard.card_back_id field and prepare_for_db() tuple length."""
from uuid import UUID
import pytest
from automana.core.models.card_catalog.card import CreateCard

pytestmark = pytest.mark.unit

MINIMAL_CARD = {
    "card_name": "Huntmaster of the Fells",
    "cmc": 4,
    "mana_cost": "{2}{R}{G}",
    "reserved": False,
    "oracle_text": "",
    "set_name": "Dark Ascension",
    "collector_number": "140",
    "rarity_name": "mythic",
    "border_color": "black",
    "frame": "2015",
    "layout": "transform",
    "promo": False,
    "digital": False,
    "keywords": [],
    "color_identity": ["R", "G"],
    "legalities": {},
    "artist": "Chris Rahn",
    "artist_ids": [UUID("00000000-0000-0000-0000-000000000001")],
    "illustration_id": UUID("00000000-0000-0000-0000-000000000001"),
    "image_uris": {},
    "games": [],
    "oversized": False,
    "booster": True,
    "full_art": False,
    "textless": False,
    "variation": False,
    "set": "dka",
    "set_id": UUID("00000000-0000-0000-0000-000000000002"),
    "id": UUID("00000000-0000-0000-0000-000000000003"),
}


def test_card_back_id_defaults_to_none():
    card = CreateCard(**MINIMAL_CARD)
    assert card.card_back_id is None


def test_card_back_id_accepted_when_provided():
    back_id = UUID("0aeebaf5-8c7d-4636-9e82-8c27447861f7")
    card = CreateCard(**MINIMAL_CARD, card_back_id=back_id)
    assert card.card_back_id == back_id


def test_prepare_for_db_has_42_values():
    card = CreateCard(**MINIMAL_CARD)
    result = card.prepare_for_db()
    assert len(result) == 42


def test_prepare_for_db_last_value_is_card_back_id():
    back_id = UUID("0aeebaf5-8c7d-4636-9e82-8c27447861f7")
    card = CreateCard(**MINIMAL_CARD, card_back_id=back_id)
    result = card.prepare_for_db()
    assert result[-1] == back_id


def test_prepare_for_db_last_value_none_when_not_set():
    card = CreateCard(**MINIMAL_CARD)
    result = card.prepare_for_db()
    assert result[-1] is None


def test_model_dump_for_sql_includes_card_back_id():
    back_id = UUID("0aeebaf5-8c7d-4636-9e82-8c27447861f7")
    card = CreateCard(**MINIMAL_CARD, card_back_id=back_id)
    dump = card.model_dump_for_sql()
    assert "card_back_id" in dump
    assert dump["card_back_id"] == str(back_id)


def test_model_dump_for_sql_card_back_id_none_when_not_set():
    card = CreateCard(**MINIMAL_CARD)
    dump = card.model_dump_for_sql()
    assert "card_back_id" in dump
    assert dump["card_back_id"] is None
