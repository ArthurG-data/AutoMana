"""Unit tests: card_repository.search() promo_type filter and facets."""
import pytest
from unittest.mock import AsyncMock
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository

pytestmark = pytest.mark.unit

_CARD_ROW = {
    "card_version_id": "aaaaaaaa-0000-0000-0000-000000000000",
    "card_name": "Ragavan",
    "rarity_name": "mythic",
    "set_name": "Modern Horizons 2",
    "set_code": "mh2",
    "cmc": 1,
    "oracle_text": "...",
    "digital": False,
    "released_at": "2021-06-18",
    "image_normal": None,
    "sort_price": 1.23,
}


def _make_repo(cards_rows, count_rows, facet_rows):
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(side_effect=[
        cards_rows,                  # 0: main search query
        count_rows,                  # 1: count query
        facet_rows,                  # 2: promo facet query
        [{"rarity_facets": []}],     # 3: rarity facet query
    ])
    # Stub _fetch_prices_for_cards so it never hits execute_query in unit tests,
    # keeping the call-index assertions stable regardless of result size.
    repo._fetch_prices_for_cards = AsyncMock(return_value={})
    return repo


@pytest.mark.asyncio
async def test_search_includes_promo_type_filter_in_sql():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": ["prerelease"]}])
    await repo.search(promo_type=["prerelease"])
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    assert "v.promo_types && $" in main_call_sql


@pytest.mark.asyncio
async def test_search_returns_promo_type_facets():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": ["buyabox", "prerelease"]}])
    result = await repo.search()
    assert result["promo_type_facets"] == ["buyabox", "prerelease"]


@pytest.mark.asyncio
async def test_search_returns_empty_facets_when_none():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": None}])
    result = await repo.search()
    assert result["promo_type_facets"] == []


@pytest.mark.asyncio
async def test_search_facet_query_uses_lateral_unnest():
    repo = _make_repo([], [{"total_count": 0}], [{"promo_type_facets": []}])
    await repo.search()
    facet_call_sql = repo.execute_query.call_args_list[2][0][0]
    assert "LATERAL unnest" in facet_call_sql
    assert "promo_type_facets" in facet_call_sql


@pytest.mark.asyncio
async def test_facet_query_excludes_promo_type_predicate():
    """Facet query must not filter on promo_types so multi-select stays discoverable."""
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": ["buyabox", "prerelease"]}])
    await repo.search(promo_type=["buyabox"])
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    facet_call_sql = repo.execute_query.call_args_list[2][0][0]
    # Main query must contain the promo_type filter
    assert "v.promo_types && $" in main_call_sql
    # Facet query must NOT contain it — so other promo types remain visible
    assert "v.promo_types && $" not in facet_call_sql


@pytest.mark.asyncio
async def test_search_sort_by_price_uses_psp_join():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": []}])
    await repo.search(sort_by="price", sort_order="asc")
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    assert "pricing.mv_card_price_spark" in main_call_sql
    assert "psp.price" in main_call_sql or "sort_price" in main_call_sql


@pytest.mark.asyncio
async def test_search_sort_by_price_desc_nulls_last():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": []}])
    await repo.search(sort_by="price", sort_order="desc")
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    assert "NULLS LAST" in main_call_sql
    assert "DESC" in main_call_sql
