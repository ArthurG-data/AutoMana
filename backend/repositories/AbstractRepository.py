from abc import ABC, abstractmethod
import asyncpg
from typing import Optional,  TypeVar,  Generic
from backend.request_handling.QueryExecutor import QueryExecutor

T =TypeVar('T')

class AbstractRepository(Generic[T], ABC):
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the entity this repository manages."""
        pass

    def __init__(self, connection: asyncpg.Connection,  executor: QueryExecutor=None):
        """
        Initialize the repository with a database connection.
        """
        self.connection = connection
        self.executor = executor

    async def execute_query(self, query, *args):
        """Execute a query that returns results"""
        if self.executor:
            return await self.executor.execute_query(query, self.connection, *args)
        else:
            # Fallback to direct connection
            return await self.connection.fetch(query, *args)
    
    async def execute_command(self, query, *args):
        """Execute a command that doesn't return results"""
        if self.executor:
            return await self.executor.execute_command(self.connection, query, *args)
        else:
            # Fallback to direct connection
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
