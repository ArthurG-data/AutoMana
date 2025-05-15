import logging, os
from psycopg2.extras import RealDictCursor, register_uuid, register_uuid
from typing import  Any, Generator
from psycopg2.extensions import connection, cursor
from psycopg2 import pool
from backend.dependancies import get_db_settings
from fastapi import Depends
from typing_extensions import Annotated

logging.basicConfig(level=logging.ERROR)

register_uuid()

db_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,  # Adjust based on your app's load
    host=get_db_settings().postgres_host,
    database=get_db_settings().postgres_db,
    user=get_db_settings().postgres_user,
    password=get_db_settings().postgres_password,
    cursor_factory=RealDictCursor,
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