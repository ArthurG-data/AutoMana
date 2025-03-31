import logging, os
from psycopg2.extras import RealDictCursor, register_uuid, register_uuid
from typing import  Any, Generator
from pathlib import Path
from dotenv import load_dotenv
from psycopg2.extensions import connection, cursor
from psycopg2 import pool

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

logging.basicConfig(level=logging.ERROR)

register_uuid()

db_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,  # Adjust based on your app's load
    host=os.getenv('POSTGRES_HOST'),
    database=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    cursor_factory=RealDictCursor
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