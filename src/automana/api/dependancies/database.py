from psycopg2.extensions import cursor
import asyncpg
from fastapi import Depends, Request
from contextlib import contextmanager, asynccontextmanager
from typing import  Any, Generator, AsyncGenerator, Annotated
from psycopg2.extensions import connection

@contextmanager
def get_sync_connection(request: Request) -> Generator[connection, Any, Any]:
    pool = request.app.state.sync_db_pool
    if pool is None:
        raise RuntimeError("Async database pool not initialized")
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@asynccontextmanager
async def get_async_connection(request: Request) -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a connection from the async pool"""
    pool = request.app.state.async_db_pool
    if pool is None:
        raise RuntimeError("Async database pool not initialized")
    async with pool.acquire() as connection:
        yield connection

def get_cursor(conn: connection) -> cursor:
    """Get cursor from connection"""
    return conn.cursor()

cursorDep = Annotated[cursor, Depends(get_sync_connection)]
asyncCursorDep = Annotated[asyncpg.Connection, Depends(get_async_connection)]
syncCursorDep = Annotated[connection, Depends(get_sync_connection)]