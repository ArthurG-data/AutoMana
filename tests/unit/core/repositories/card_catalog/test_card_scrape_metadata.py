import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository


@pytest.mark.asyncio
async def test_get_scrape_metadata_returns_expected_fields():
    mock_conn = AsyncMock()
    repo = CardReferenceRepository(connection=mock_conn, executor=None)
    card_id = uuid4()
    fake_row = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": ["showcase"],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    with patch.object(repo, "execute_query", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = [fake_row]
        result = await repo.get_scrape_metadata(card_id)

    assert result is not None
    assert result["card_name"] == "Sheoldred, the Apocalypse"
    assert result["frame_effects"] == ["showcase"]
    assert result["border_color_name"] == "black"


@pytest.mark.asyncio
async def test_get_scrape_metadata_returns_none_when_not_found():
    mock_conn = AsyncMock()
    repo = CardReferenceRepository(connection=mock_conn, executor=None)
    with patch.object(repo, "execute_query", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = []
        result = await repo.get_scrape_metadata(uuid4())
    assert result is None
