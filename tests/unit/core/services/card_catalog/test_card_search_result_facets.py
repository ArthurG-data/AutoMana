"""Unit tests for CardSearchResult carries promo_type_facets."""
import pytest
from automana.core.services.card_catalog.card_service import CardSearchResult

pytestmark = pytest.mark.unit


def test_card_search_result_default_facets():
    result = CardSearchResult(cards=[], total_count=0)
    assert result.promo_type_facets == []


def test_card_search_result_with_facets():
    result = CardSearchResult(cards=[], total_count=0, promo_type_facets=["buyabox", "prerelease"])
    assert result.promo_type_facets == ["buyabox", "prerelease"]
