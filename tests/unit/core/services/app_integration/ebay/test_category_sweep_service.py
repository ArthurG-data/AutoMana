"""Unit tests for category sweep internal matching logic."""
from __future__ import annotations

import pytest


def _make_lookup(spid, card_name, set_code="DMU"):
    return {spid: {"source_product_id": spid, "card_name": card_name, "set_code": set_code}}


def test_match_item_returns_best_scoring_card():
    from automana.core.services.app_integration.ebay.category_sweep_service import _match_item

    lookup = {}
    lookup.update(_make_lookup(1, "Sheoldred, the Apocalypse", "DMU"))
    lookup.update(_make_lookup(2, "Atraxa, Praetors' Voice", "ONE"))

    item = {"item_id": "X", "title": "Sheoldred the Apocalypse DMU NM MTG", "price": 18.99, "currency": "USD"}
    spid, score, card = _match_item(item, lookup)

    assert spid == 1
    assert score >= 0.5
    assert card["card_name"] == "Sheoldred, the Apocalypse"


def test_match_item_returns_none_below_threshold():
    from automana.core.services.app_integration.ebay.category_sweep_service import _match_item

    lookup = _make_lookup(1, "Sheoldred, the Apocalypse", "DMU")
    item = {"item_id": "Y", "title": "MTG lot 50 random cards mixed", "price": 5.0}
    spid, score, card = _match_item(item, lookup)

    assert spid is None


def test_match_item_empty_lookup_returns_none():
    from automana.core.services.app_integration.ebay.category_sweep_service import _match_item

    spid, score, card = _match_item({"title": "Sheoldred DMU"}, {})
    assert spid is None
    assert card is None
