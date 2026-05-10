"""Unit tests for CardReferenceRepository.get()"""
import pytest
from unittest.mock import AsyncMock
from uuid import UUID
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository

pytestmark = pytest.mark.unit

_CARD_ID = UUID("11111111-1111-1111-1111-111111111111")

_BASE_ROW = {
    "card_version_id": str(_CARD_ID),
    "card_name": "Sheoldred",
    "rarity_name": "rare",
    "set_name": "March of the Machine",
    "set_code": "mom",
    "cmc": 4,
    "oracle_text": "...",
    "released_at": "2023-04-21",
    "digital": False,
    "image_large": None,
}


def _make_repo(rows):
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_get_returns_available_finishes():
    row = {**_BASE_ROW, "available_finishes": ["nonfoil", "foil"]}
    repo = _make_repo([row])
    result = await repo.get(card_id=_CARD_ID)
    assert result["available_finishes"] == ["nonfoil", "foil"]


@pytest.mark.asyncio
async def test_get_returns_empty_list_when_no_finish_rows():
    row = {**_BASE_ROW, "available_finishes": []}
    repo = _make_repo([row])
    result = await repo.get(card_id=_CARD_ID)
    assert result["available_finishes"] == []


@pytest.mark.asyncio
async def test_get_returns_none_when_card_not_found():
    repo = _make_repo([])
    result = await repo.get(card_id=UUID("00000000-0000-0000-0000-000000000000"))
    assert result is None


@pytest.mark.asyncio
async def test_get_query_lowercases_finish_codes():
    repo = _make_repo([{**_BASE_ROW, "available_finishes": []}])
    await repo.get(card_id=_CARD_ID)
    sql = repo.execute_query.await_args.args[0]
    assert "LOWER(cf.code)" in sql
    assert "card_version_finish" in sql
    assert "card_catalog.card_finished" in sql
