from backend.services.shop_data_ingestion.db import QueryExecutor, ErrorHandler
from backend.database.get_database import get_connection, get_async_pool_connection

def get_sync_query_executor():
    """Dependency function that provides a SyncQueryExecutor instance."""
    handler = ErrorHandler.Psycopg2ExceptionHandler()
    conn = next(get_connection())  # Get a connection from your connection pool
    return QueryExecutor.SyncQueryExecutor(conn, handler)

def get_async_query_executor():
    """Dependency function that provides an AsyncQueryExecutor instance."""
    handler = ErrorHandler.Psycopg2ExceptionHandler()
    conn = next(get_async_pool_connection())  # Get a connection from your connection pool
    return QueryExecutor.AsyncQueryExecutor(conn, handler)

