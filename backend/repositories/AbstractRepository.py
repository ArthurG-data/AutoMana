from abc import ABC, abstractmethod
import asyncpg
from typing import Optional,  TypeVar,  Generic

T =TypeVar('T')

class AbstractRepository(Generic[T], ABC):
    @abstractmethod
    def __init__(self, connection: asyncpg.Connection):
        """
        Initialize the repository with a database connection.
        """
        self.connection = connection

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
