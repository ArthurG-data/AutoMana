from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
import asyncpg, psycopg2
import logging
from typing import Optional,  TypeVar,  Generic, Union
from automana.core.QueryExecutor import QueryExecutor

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
            
    async def execute_query(self, query, *args):
        """Execute a query that returns results"""
        if self.executor:
            logger.debug("Executing query with executor")
            return await self.executor.execute_query(self.connection, query, args)
        else:
            logger.debug("Executing query without executor")
            # Fallback to direct connection
            return await self.connection.fetch(query, *args)
    
    async def execute_command(self, query, *args):
        """Execute a command that doesn't return results"""
        if self.executor:
            logger.debug("Executing query with executor")
            return await self.executor.execute_command(self.connection, query, args)
        else:
            # Fallback to direct connection
            logger.debug("Executing query without executor")
            return await self.connection.execute(query, *args)
        
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
