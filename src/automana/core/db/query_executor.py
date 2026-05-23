from typing import TypeVar, List, Tuple, Any
from abc import ABC, abstractmethod
from psycopg2.extensions import connection
import asyncpg
import inspect

import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')

class QueryExecutor(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the executor."""
        pass

    @abstractmethod
    def execute_command(
        self,
        query: str,
        params: Tuple[Any, ...] = ()
    ) -> None:
        logger.debug(f"Executing query: {query} with params: {params}")
        """
        Execute a statement that does not return rows (INSERT/UPDATE/DELETE/CALL).
        Must commit or rollback internally.
        """
        
    @abstractmethod
    def execute_query(
        self,
        query: str,
        params: Tuple[Any, ...] = ()
    ) -> List[T]:
        logger.debug(f"Executing query: {query} with params: {params}")

        """
        Execute a SELECT or other row-returning statement.
        Returns all rows as a list of tuples.
        """

    @abstractmethod
    def execute_many(
        self,
        query: str,
        rows: List[Tuple[Any, ...]],
    ) -> None:
        """Execute a bulk command (INSERT/UPDATE) against a list of row tuples."""
        pass

class SyncQueryExecutor(QueryExecutor):
    def __init__(self, error_Handler: Any = print):
        self.handle_error = error_Handler

    def name(self) -> str:
        return "SyncQueryExecutor"

    def execute_command(self, connection: connection, query: str, values: Tuple[Any, ...]) -> None:
        logger.debug(f"Executing query: {query} with values: {values}")
        """Side effect, but return nothing"""
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                connection.commit()
        except Exception as e:
            connection.rollback()
            raise
        
    def execute_query(
        self,
        connection: connection,
        query: str,
        params: Tuple[Any, ...] = ()
    ) -> List[T]:
        logger.debug(f"Executing query: {query} with values: {params}")
        with connection.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return rows

    def execute_many(
        self,
        connection: connection,
        query: str,
        rows: List[Tuple[Any, ...]],
    ) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.executemany(query, rows)
                connection.commit()
        except Exception:
            connection.rollback()
            raise


class AsyncQueryExecutor(QueryExecutor):
    def __init__(self, error_handler: Any = print):
        self.error_handler = error_handler
    
    def name(self) -> str:
        return "AsyncQueryExecutor"

    async def _handle_exception(self, exc: Exception) -> None:
        """Support callable handlers and handler objects (handle_async/handle)."""
        handler = self.error_handler

        if callable(handler):
            result = handler(exc)
            if inspect.isawaitable(result):
                await result
            return

        if hasattr(handler, "handle_async"):
            await handler.handle_async(exc)
            return

        if hasattr(handler, "handle"):
            handler.handle(exc)
            return

        logger.error("Invalid error handler configured for AsyncQueryExecutor")
        raise exc
    
    async def execute_command(self, connection: asyncpg.Connection, query: str, params: Tuple[Any, ...] = ()) -> None:
        try:
            record = await connection.execute(query, *params)
            return record
        except asyncpg.InFailedSQLTransactionError:
            # A prior error left this PostgreSQL session in an aborted transaction
            # (common after postgres restarts hit a pool connection mid-task).
            # Roll back to clear the state and retry once.
            await connection.execute("ROLLBACK")
            return await connection.execute(query, *params)
        except Exception as e:
            await self._handle_exception(e)
            raise

    async def execute_query(
        self,
        connection: asyncpg.Connection,
        query: str,
        params: Tuple[Any, ...] = ()
    ) -> List[T]:
        try:
            records = await connection.fetch(query, *params)
            return [dict(row) for row in records]
        except asyncpg.InFailedSQLTransactionError:
            await connection.execute("ROLLBACK")
            records = await connection.fetch(query, *params)
            return [dict(row) for row in records]
        except Exception as e:
            await self._handle_exception(e)
            raise

    async def execute_many(
        self,
        connection: asyncpg.Connection,
        query: str,
        rows: List[Tuple[Any, ...]],
    ) -> None:
        try:
            await connection.executemany(query, rows)
        except asyncpg.InFailedSQLTransactionError:
            await connection.execute("ROLLBACK")
            await connection.executemany(query, rows)
        except Exception as e:
            await self._handle_exception(e)
            raise
