from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
import asyncpg, psycopg2
import logging
from typing import Optional,  TypeVar,  Generic, Union
from automana.core.db.query_executor import QueryExecutor

logger = logging.getLogger(__name__)

T =TypeVar('T')

class AbstractRepository(Generic[T], ABC):
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the entity this repository manages."""
        pass

    def __init__(self, connection: Union[asyncpg.Connection, psycopg2.extensions.connection],  executor: QueryExecutor=None):
        """
        Initialize the repository with a database connection.
        """
        self.connection = connection
        self.executor = executor
        self._thread_pool = ThreadPoolExecutor(max_workers=4)


    def execute_query_sync(self, query, *args):
        """Execute a query that returns results"""
        if self.executor:
            logger.debug("Executing query with executor")
            return self.executor.execute_query(self.connection, query, *args)
        else:
            logger.debug("Executing query without executor")
            # Fallback to direct connection
            with self.connection.cursor() as cursor:
                cursor.execute(query, args)
                return cursor.fetchall()
    
    def execute_command_sync(self, query, *args):
        """Execute a command that doesn't return results"""
        if self.executor:
            logger.debug("Executing query with executor")
            return self.executor.execute_command(self.connection, query, *args)
        else:
            # Fallback to direct connection
            logger.debug("Executing query without executor")
            with self.connection.cursor() as cursor:
                cursor.execute(query, args)
                self.connection.commit()
                return None
            
    async def execute_query(self, query, values=()):
        """Execute a query that returns results"""
        if self.executor:
            logger.debug("Executing query with executor")
            return await self.executor.execute_query(self.connection, query, values)
        else:
            logger.debug("Executing query without executor")
            return await self.connection.fetch(query, *values)

    async def execute_command(self, query, values=()):
        """Execute a command that doesn't return results"""
        if self.executor:
            logger.debug("Executing query with executor")
            return await self.executor.execute_command(self.connection, query, values)
        else:
            logger.debug("Executing query without executor")
            return await self.connection.execute(query, *values)

    async def execute_many(self, query: str, rows: list) -> None:
        if self.executor:
            logger.debug("Executing bulk command with executor")
            return await self.executor.execute_many(self.connection, query, rows)
        else:
            logger.debug("Executing bulk command without executor")
            return await self.connection.executemany(query, rows)

    async def execute_fetchrow(self, query: str, values: tuple = ()):
        # QueryExecutor doesn't define fetchrow — goes direct to connection.
        return await self.connection.fetchrow(query, *values)

    async def execute_fetchval(self, query: str, values: tuple = ()):
        # QueryExecutor doesn't define fetchval — goes direct to connection.
        return await self.connection.fetchval(query, *values)

    async def execute_copy_to_table(self, table_name: str, source, **kwargs):
        # COPY is asyncpg-specific; not routable through QueryExecutor.
        return await self.connection.copy_to_table(
            table_name=table_name, source=source, **kwargs
        )

    async def execute_copy_records_to_table(
        self, table_name: str, *, records, columns, schema_name: str
    ):
        # COPY is asyncpg-specific; not routable through QueryExecutor.
        return await self.connection.copy_records_to_table(
            table_name, records=records, columns=columns, schema_name=schema_name
        )

    async def execute_procedure(
        self, proc_name: str, args: tuple = (), timeout: float | None = None
    ) -> None:
        """Execute a stored procedure via CALL. Use service-level command_timeout for long ops."""
        placeholders = ", ".join(f"${i + 1}" for i in range(len(args)))
        call_stmt = f"CALL {proc_name}({placeholders})"
        await self.connection.execute(call_stmt, *args, timeout=timeout)

    def transaction(self):
        """Return an asyncpg transaction context manager."""
        return self.connection.transaction()

    async def add_listener(self, channel: str, callback) -> None:
        await self.connection.add_listener(channel, callback)

    async def remove_listener(self, channel: str, callback) -> None:
        await self.connection.remove_listener(channel, callback)

    @abstractmethod
    async def add(self, item: T) -> None:
        pass

    @abstractmethod
    async def get(self, id: int) -> Optional[T]:
        pass

    @abstractmethod
    async def update(self, item: T) -> None:
        pass

    @abstractmethod
    async def delete(self, id: int) -> None:
        pass

    @abstractmethod
    async def list(self, items : T) -> list[T]:
        """
        List all items of type T.
        """
        pass
