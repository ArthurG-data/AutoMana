from contextlib import contextmanager, asynccontextmanager
from typing import Type, TypeVar, Callable, List, Optional
from abc import ABC, abstractmethod
from typing import List, Any, Optional, Tuple
from psycopg2.extensions import connection
import asyncpg

T = TypeVar('T')

class QueryExecutor(ABC):
    @abstractmethod
    def execute_command(
        self,
        query:str, 
        params: Tuple[Any, ...]=()
    )->None:
        """
        Execute a statement that does not return rows (INSERT/UPDATE/DELETE/CALL).
        Must commit or rollback internally.
        """
        
    @abstractmethod
    def execute_query(
        self, 
        query: str, 
        params: Tuple[Any, ...] = (),
        mapper: Optional[Callable[..., T]] = None
    ) -> List[T]:
        
        """
        Execute a SELECT or other row-returning statement.
        Returns all rows as a list of tuples.
        """

class SyncQueryExecutor(QueryExecutor):
    def __init__(self, conn: connection, error_Handler : Any=print):
        self.conn = conn
        self.handle_error =  error_Handler 

    def execute_command(self, query : str, values : Tuple[any])->None:
        """Side effect, but return nothing"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, values)
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise
        
    def execute_query(
        self, 
        query: str, 
        params: Tuple[Any, ...] = (),
        mapper: Optional[Callable[..., T]] = None
    ) -> List[T]:
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        if mapper:
            return [mapper(*row) for row in rows]
        return rows
    
    @contextmanager
    def transaction(self):
        try:
            yield
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            self.handle_error(e)
            raise

class AsyncQueryExecutor(QueryExecutor):
    def __init__(self, pool: asyncpg.Pool, error_handler: Any = print):
        self.pool = pool
        self.error_handler = error_handler
    
    async def execute_command(self, query: str, params: Tuple[Any, ...] = ()) -> None:
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(query, *params)
            except Exception as e:
                self.error_handler(e)
                raise
    async def execute_query(
        self, 
        query: str, 
        params: Tuple[Any, ...] = (),
        mapper: Optional[Callable[..., T]] = None
    ) -> List[T]:
        async with self.pool.acquire() as conn:
            try:
                records = await conn.fetch(query, *params)
                if mapper:
                    return [mapper(*row) for row in records]
                return [tuple(r) for r in records]
            except Exception as e:
                self.error_handler(e)
                raise

    @asynccontextmanager
    async def transaction(self):
        """
        Usage:
            async with executor.transaction() as conn:
                await conn.execute(...)
                await conn.execute(...)
        """
        async with self.pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                yield conn
                await tx.commit()
            except Exception as e:
                await tx.rollback()
                self.handle_error(e)
                raise
    
