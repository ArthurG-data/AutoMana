import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_repo():
    from automana.core.repositories.app_integration.mtg_stock.identifier_repository import (
        MtgstockIdentifierRepository,
    )
    repo = MtgstockIdentifierRepository.__new__(MtgstockIdentifierRepository)
    repo.execute_query = AsyncMock()
    repo.execute_command = AsyncMock()
    repo.execute_many = AsyncMock()
    repo.execute_fetchval = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_get_mtgstock_ref_id_returns_int():
    repo = _make_repo()
    repo.execute_fetchval.return_value = 8
    result = await repo.get_mtgstock_ref_id()
    assert result == 8
    repo.execute_fetchval.assert_awaited_once()
    assert "mtgstock_id" in repo.execute_fetchval.call_args[0][0]


@pytest.mark.asyncio
async def test_get_existing_mapped_print_ids_returns_set():
    repo = _make_repo()
    repo.execute_fetchval.return_value = 8
    repo.execute_query.return_value = [{"value": 1001}, {"value": 2002}]
    result = await repo.get_existing_mapped_print_ids()
    assert result == {1001, 2002}


@pytest.mark.asyncio
async def test_fetch_by_scryfall_returns_mapping():
    repo = _make_repo()
    repo.execute_query.return_value = [
        {"scryfall_id": "abc-123", "card_version_id": "uuid-1"},
    ]
    result = await repo.fetch_by_scryfall(["abc-123", "def-456"])
    assert result == {"abc-123": "uuid-1"}
    assert "scryfall_id" in repo.execute_query.call_args[0][0]


@pytest.mark.asyncio
async def test_fetch_by_tcgplayer_returns_mapping():
    repo = _make_repo()
    repo.execute_query.return_value = [
        {"tcg_id": "576888", "card_version_id": "uuid-2"},
    ]
    result = await repo.fetch_by_tcgplayer(["576888"])
    assert result == {"576888": "uuid-2"}
    assert "tcgplayer_id" in repo.execute_query.call_args[0][0]


@pytest.mark.asyncio
async def test_fetch_by_set_collector_returns_mapping():
    repo = _make_repo()
    repo.execute_query.return_value = [
        {"set_code": "dsk", "collector_number": "232", "card_version_id": "uuid-3"},
    ]
    result = await repo.fetch_by_set_collector([("DSK", "232")])
    assert ("DSK", "232") in result
    assert result[("DSK", "232")] == "uuid-3"


@pytest.mark.asyncio
async def test_upsert_mtgstock_id_mappings_calls_execute_many():
    repo = _make_repo()
    repo.execute_fetchval.return_value = 8
    mappings = [
        {"card_version_id": "uuid-1", "print_id": 1001},
        {"card_version_id": "uuid-2", "print_id": 1002},
    ]
    result = await repo.upsert_mtgstock_id_mappings(mappings)
    assert result == 2
    repo.execute_many.assert_awaited_once()
    rows = repo.execute_many.call_args[0][1]
    assert len(rows) == 2
    assert rows[0] == ("uuid-1", 8, "1001")
    assert rows[1] == ("uuid-2", 8, "1002")
