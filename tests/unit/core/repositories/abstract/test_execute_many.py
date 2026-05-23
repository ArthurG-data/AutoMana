"""Unit tests for QueryExecutor.execute_many implementations."""
from __future__ import annotations

from unittest.mock import AsyncMock, call
import asyncpg
import pytest

from automana.core.QueryExecutor import AsyncQueryExecutor


class TestAsyncQueryExecutorExecuteMany:
    async def test_delegates_to_connection_executemany(self):
        conn = AsyncMock()
        executor = AsyncQueryExecutor()
        rows = [("a", 1), ("b", 2)]

        await executor.execute_many(conn, "INSERT INTO t VALUES ($1, $2)", rows)

        conn.executemany.assert_awaited_once_with(
            "INSERT INTO t VALUES ($1, $2)", rows
        )

    async def test_retries_after_failed_transaction_error(self):
        conn = AsyncMock()
        conn.executemany.side_effect = [
            asyncpg.InFailedSQLTransactionError("aborted"),
            None,
        ]
        executor = AsyncQueryExecutor()

        await executor.execute_many(conn, "INSERT INTO t VALUES ($1)", [("x",)])

        assert conn.execute.await_args_list == [call("ROLLBACK")]
        assert conn.executemany.await_count == 2

    async def test_reraises_unknown_exception(self):
        conn = AsyncMock()
        conn.executemany.side_effect = RuntimeError("boom")
        executor = AsyncQueryExecutor()

        with pytest.raises(RuntimeError, match="boom"):
            await executor.execute_many(conn, "INSERT INTO t VALUES ($1)", [("x",)])
