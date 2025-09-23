import logging, os
from psycopg2.extras import RealDictCursor, register_uuid, register_uuid
from typing import  Any, Generator
from psycopg2.extensions import connection, cursor
from psycopg2 import pool
from backend.dependancies.settings import get_db_settings
from fastapi import Depends
from typing_extensions import Annotated

logging.basicConfig(level=logging.ERROR)

register_uuid()

import asyncpg
from typing import AsyncGenerator
import os

async_db_pool = None

async def init_async_pool():
    """Initialize the async connection pool"""
    global async_db_pool
    if async_db_pool is None:
        async_db_pool = await asyncpg.create_pool(
            host=get_db_settings().postgres_host,
            port=os.getenv("DB_PORT", 5432),
            user=get_db_settings().postgres_user,
            password=get_db_settings().postgres_password,
            database=get_db_settings().postgres_db,
            min_size=1,
            max_size=10,  # Adjust based on your app's load
            server_settings={'client_encoding': 'UTF8'}
        )
    return async_db_pool


async def get_async_pool_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a connection from the async pool"""
    pool = await init_async_pool()
    async with pool.acquire() as connection:
        yield connection


db_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,  # Adjust based on your app's load
    host=get_db_settings().postgres_host,
    database=get_db_settings().postgres_db,
    user=get_db_settings().postgres_user,
    password=get_db_settings().postgres_password,
    cursor_factory=RealDictCursor,
    options='-c client_encoding=UTF8'
)


def get_connection() -> Generator[connection, Any, Any]:
    db = db_pool.getconn() 
    try:
        yield db
    finally:
        db_pool.putconn(db)

    
def get_cursor(connection : connection) -> cursor:
    pointer = connection.cursor()
    try:
        return pointer
    except Exception as e:
        raise

cursorDep = Annotated[connection, Depends(get_connection)]
asyncCursorDep = Annotated[asyncpg.Connection, Depends(get_async_pool_connection)]