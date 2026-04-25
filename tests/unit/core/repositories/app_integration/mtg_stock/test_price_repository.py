"""
Tests for src/automana/core/repositories/app_integration/mtg_stock/price_repository.py

Focus: new call_resolve_price_rejects wrapper. The critical thing to verify is
that it invokes `SELECT pricing.resolve_price_rejects(...)` (the proc is a
FUNCTION, not a PROCEDURE — `CALL` would fail at runtime).
"""
from unittest.mock import AsyncMock

import pytest

from automana.core.repositories.app_integration.mtg_stock.price_repository import (
    PriceRepository,
)


class TestCallResolvePriceRejects:
    async def test_invokes_function_via_select_with_defaults(self):
        connection = AsyncMock()
        connection.fetchrow.return_value = {"rows_resolved": 7}
        repo = PriceRepository(connection=connection)

        result = await repo.call_resolve_price_rejects()

        assert result == 7
        connection.fetchrow.assert_awaited_once()
        sql = connection.fetchrow.await_args.args[0]
        # Must be SELECT-invoked, not CALL — resolve_price_rejects is a FUNCTION.
        assert "SELECT" in sql.upper()
        assert "pricing.resolve_price_rejects" in sql
        assert "CALL" not in sql.upper()
        # Default kwargs pass through positionally.
        assert connection.fetchrow.await_args.args[1:] == (50000, True)

    async def test_invokes_with_custom_limit_and_flag(self):
        connection = AsyncMock()
        connection.fetchrow.return_value = {"rows_resolved": 1234}
        repo = PriceRepository(connection=connection)

        result = await repo.call_resolve_price_rejects(limit=500, only_unresolved=False)

        assert result == 1234
        assert connection.fetchrow.await_args.args[1:] == (500, False)

    async def test_returns_zero_when_function_returns_null(self):
        """bigint FUNCTIONs can return NULL; wrapper should coerce to 0."""
        connection = AsyncMock()
        connection.fetchrow.return_value = {"rows_resolved": None}
        repo = PriceRepository(connection=connection)

        assert await repo.call_resolve_price_rejects() == 0

    async def test_returns_zero_when_no_row(self):
        connection = AsyncMock()
        connection.fetchrow.return_value = None
        repo = PriceRepository(connection=connection)

        assert await repo.call_resolve_price_rejects() == 0
