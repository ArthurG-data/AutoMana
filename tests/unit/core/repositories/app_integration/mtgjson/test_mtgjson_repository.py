import pytest
from unittest.mock import AsyncMock, MagicMock

from automana.core.repositories.app_integration.mtgjson.mtgjson_repository import MtgjsonRepository


def _make_repo() -> MtgjsonRepository:
    repo = MtgjsonRepository.__new__(MtgjsonRepository)
    repo.execute_fetchval = AsyncMock()
    repo.execute_command = AsyncMock()
    return repo


class TestUpsertMtgjsonIdMappings:
    @pytest.mark.asyncio
    async def test_empty_pairs_returns_zero_without_db_call(self):
        repo = _make_repo()
        result = await repo.upsert_mtgjson_id_mappings([])
        assert result == 0
        repo.execute_fetchval.assert_not_called()

    @pytest.mark.asyncio
    async def test_primary_insert_count_returned(self):
        repo = _make_repo()
        repo.execute_fetchval.return_value = 2

        result = await repo.upsert_mtgjson_id_mappings([
            ("uuid-front-1", "scryfall-1"),
            ("uuid-front-2", "scryfall-2"),
        ])

        assert result == 2
        repo.execute_fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_alias_insert_called_after_primary(self):
        """alias execute_command must be called after execute_fetchval, not before."""
        repo = _make_repo()
        call_order = []
        repo.execute_fetchval = AsyncMock(
            side_effect=lambda *a, **kw: call_order.append("fetchval") or 1
        )
        repo.execute_command = AsyncMock(
            side_effect=lambda *a, **kw: call_order.append("execute")
        )

        await repo.upsert_mtgjson_id_mappings([("uuid-a", "scryfall-a")])

        assert call_order == ["fetchval", "execute"]

    @pytest.mark.asyncio
    async def test_alias_insert_receives_correct_arrays(self):
        repo = _make_repo()
        repo.execute_fetchval.return_value = 0

        pairs = [("uuid-back-1", "scryfall-1"), ("uuid-back-2", "scryfall-2")]
        await repo.upsert_mtgjson_id_mappings(pairs)

        alias_call = repo.execute_command.call_args
        # execute_command(query, values) — values is a tuple of two lists
        _, values = alias_call[0][0], alias_call[0][1]
        assert list(values[0]) == ["uuid-back-1", "uuid-back-2"]
        assert list(values[1]) == ["scryfall-1", "scryfall-2"]


class TestTruncateStagingAfterPromotion:
    @pytest.mark.asyncio
    async def test_returns_row_count_before_truncate(self):
        repo = _make_repo()
        repo.execute_fetchval.return_value = 42

        result = await repo.truncate_staging_after_promotion()

        assert result == 42
        repo.execute_command.assert_called_once_with(
            "TRUNCATE pricing.mtgjson_card_prices_staging", ()
        )

    @pytest.mark.asyncio
    async def test_returns_zero_and_skips_truncate_when_empty(self):
        repo = _make_repo()
        repo.execute_fetchval.return_value = 0

        result = await repo.truncate_staging_after_promotion()

        assert result == 0
        repo.execute_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_count_treated_as_zero(self):
        repo = _make_repo()
        repo.execute_fetchval.return_value = None

        result = await repo.truncate_staging_after_promotion()

        assert result == 0
        repo.execute_command.assert_not_called()
