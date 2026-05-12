import pytest
from unittest.mock import AsyncMock
from datetime import date
from uuid import uuid4

ROWS = [
    {
        "set_id": uuid4(),
        "set_name": "Murders at Karlov Manor",
        "set_code": "mkm",
        "set_type": "expansion",
        "card_count": 286,
        "released_at": date(2024, 2, 9),
        "icon_svg_uri": "https://svgs.scryfall.io/sets/mkm.svg",
        "parent_set_code": None,
        "key_art_uri": "https://cards.scryfall.io/art_crop/front/a/b/ab12.jpg",
    },
    {
        "set_id": uuid4(),
        "set_name": "Arena Base Set",
        "set_code": "anb",
        "set_type": "alchemy",
        "card_count": 60,
        "released_at": date(2020, 6, 25),
        "icon_svg_uri": None,
        "parent_set_code": None,
        "key_art_uri": None,
    },
]


@pytest.mark.asyncio
async def test_browse_returns_set_browse_items():
    from automana.core.services.card_catalog import set_service
    from automana.core.models.card_catalog.set import SetBrowseItem

    mock_repo = AsyncMock()
    mock_repo.browse.return_value = ROWS

    result = await set_service.browse_sets(set_repository=mock_repo)

    assert len(result) == 2
    assert all(isinstance(item, SetBrowseItem) for item in result)
    assert result[0].set_code == "mkm"
    assert result[1].icon_svg_uri is None


@pytest.mark.asyncio
async def test_browse_passes_through_key_art_uri():
    from automana.core.services.card_catalog import set_service

    mock_repo = AsyncMock()
    mock_repo.browse.return_value = ROWS

    result = await set_service.browse_sets(set_repository=mock_repo)

    assert result[0].key_art_uri == "https://cards.scryfall.io/art_crop/front/a/b/ab12.jpg"
    assert result[1].key_art_uri is None


@pytest.mark.asyncio
async def test_browse_propagates_repo_error():
    from automana.core.services.card_catalog import set_service

    mock_repo = AsyncMock()
    mock_repo.browse.side_effect = RuntimeError("db gone")

    with pytest.raises(Exception):
        await set_service.browse_sets(set_repository=mock_repo)
