"""Unit tests: search_cards threads promo_type and surfaces promo_type_facets."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from automana.core.services.card_catalog.card_service import search_cards

pytestmark = pytest.mark.unit

_RAW = {
    "cards": [],
    "total_count": 0,
    "promo_type_facets": ["buyabox", "prerelease"],
}


@pytest.mark.asyncio
async def test_search_cards_forwards_promo_type_facets():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=_RAW)
    with patch("automana.core.services.card_catalog.card_service.get_from_cache", return_value=None), \
         patch("automana.core.services.card_catalog.card_service.set_to_cache", new_callable=AsyncMock):
        result = await search_cards(card_repository=repo, promo_type=["buyabox"])
    repo.search.assert_called_once()
    call_kwargs = repo.search.call_args.kwargs
    assert call_kwargs.get("promo_type") == ["buyabox"]
    assert result.promo_type_facets == ["buyabox", "prerelease"]


@pytest.mark.asyncio
async def test_search_cards_facets_in_cache():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=_RAW)
    captured_cache = {}

    async def fake_set(key, data, **kw):
        captured_cache.update(data)

    with patch("automana.core.services.card_catalog.card_service.get_from_cache", return_value=None), \
         patch("automana.core.services.card_catalog.card_service.set_to_cache", side_effect=fake_set):
        await search_cards(card_repository=repo)

    assert "promo_type_facets" in captured_cache
    assert captured_cache["promo_type_facets"] == ["buyabox", "prerelease"]
