from contextlib import contextmanager, asynccontextmanager
import re
from typing import  TypeVar, Callable, List, Optional
from abc import ABC, abstractmethod
from typing import List, Any, Optional, Tuple
from fastapi import params
from psycopg2.extensions import connection
import asyncpg

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


class AsyncQueryExecutor(QueryExecutor):
    def __init__(self, error_handler: Any = print):
        self.handle_error = error_handler
    
    def name(self) -> str:
        return "AsyncQueryExecutor"
    
    async def execute_command(self, connection: asyncpg.Connection, query: str, params: Tuple[Any, ...] = ()) -> None:
        try:
            record = await connection.execute(query, *params)
            return record
        except Exception as e:
            self.handle_error.handle(e)
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
        except Exception as e:
            self.handle_error.handle(e)
            raise

class SQLAlchemyQueryExecutor(QueryExecutor):
    def __init__(self, error_handler: Any = print):
        self.handle_error = error_handler

    def name(self) -> str:
        return "SQLAlchemyQueryExecutor"
    
    def _convert_postgres_params(self, query: str, params: Tuple[Any, ...]) -> tuple:
        """Convert PostgreSQL $1, $2, etc. parameters to SQLAlchemy :param_0, :param_1 format"""
        if not params:
            return query, {}
        
        # Convert params tuple to dict
        param_dict = {f'param_{i}': param for i, param in enumerate(params)}
        
        # Replace $1::TYPE, $2::TYPE, etc. with CAST(:param_0 AS TYPE), CAST(:param_1 AS TYPE), etc.
        # This handles PostgreSQL cast syntax properly
        def replace_param_with_cast(match):
            param_num = int(match.group(1)) - 1  # Convert from 1-based to 0-based
            cast_type = match.group(2)  # The type after ::
            return f'CAST(:param_{param_num} AS {cast_type})'
        
        # First handle parameters with cast syntax: $1::TYPE
        converted_query = re.sub(r'\$(\d+)::(\w+)', replace_param_with_cast, query)
        
        # Then handle any remaining plain parameters: $1, $2, etc.
        def replace_plain_param(match):
            param_num = int(match.group(1)) - 1  # Convert from 1-based to 0-based
            return f':param_{param_num}'
        
        converted_query = re.sub(r'\$(\d+)', replace_plain_param, converted_query)
        
        return converted_query, param_dict



    def execute_command(self, connection, query: str, params: Tuple[Any, ...] = ()) -> None:
        """Execute a statement that does not return rows (INSERT/UPDATE/DELETE/CALL)."""
        logger.debug(f"Executing command: {query} with params: {params}")
        try:
            from sqlalchemy import text
            
            if isinstance(params, tuple) and params:
                # Use the conversion function
                converted_query, param_dict = self._convert_postgres_params(query, params)
                logger.debug(f"Converted query: {converted_query}")
                logger.debug(f"Converted params: {param_dict}")
                result = connection.execute(text(converted_query), param_dict)
            else:
                result = connection.execute(text(query), params if isinstance(params, dict) else {})

            return result
        except Exception as e:
            self.handle_error(e)
            raise
        
    def execute_query(self, connection, query: str, params: Tuple[Any, ...] = ()) -> List[T]:
        """Execute a SELECT or other row-returning statement."""
        logger.debug(f"Executing query: {query} with params: {params}")
        try:
            from sqlalchemy import text
            
            if isinstance(params, tuple) and params:
                # Use the conversion function
                converted_query, param_dict = self._convert_postgres_params(query, params)
                logger.debug(f"Converted query: {converted_query}")
                logger.debug(f"Converted params: {param_dict}")
                result = connection.execute(text(converted_query), param_dict)
            else:
                result = connection.execute(text(query), params if isinstance(params, dict) else {})

            # Fetch all rows and convert to list of dicts
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows] if rows else []
        except Exception as e:
            self.handle_error(e)
            raise
