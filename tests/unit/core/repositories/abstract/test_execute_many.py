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


from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)


class _ConcreteRepo(AbstractRepository[dict]):
    """Minimal concrete subclass to satisfy abstract methods."""
    @property
    def name(self) -> str:
        return "test"

    async def add(self, item): pass
    async def get(self, id): return None
    async def update(self, item): pass
    async def delete(self, id): pass
    async def list(self, items=None): return []


class TestAbstractRepositoryExecuteMany:
    async def test_routes_through_executor_when_present(self):
        conn = AsyncMock()
        executor = AsyncMock()
        repo = _ConcreteRepo(connection=conn, executor=executor)
        rows = [("a", 1)]

        await repo.execute_many("INSERT INTO t VALUES ($1, $2)", rows)

        executor.execute_many.assert_awaited_once_with(
            conn, "INSERT INTO t VALUES ($1, $2)", rows
        )
        conn.executemany.assert_not_awaited()

    async def test_falls_back_to_connection_when_no_executor(self):
        conn = AsyncMock()
        repo = _ConcreteRepo(connection=conn, executor=None)
        rows = [("x",)]

        await repo.execute_many("INSERT INTO t VALUES ($1)", rows)

        conn.executemany.assert_awaited_once_with(
            "INSERT INTO t VALUES ($1)", rows
        )
