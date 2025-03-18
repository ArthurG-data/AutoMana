import logging, os
from psycopg2.extras import RealDictCursor
from fastapi import Depends
from typing import Annotated, Any, Sequence,Generator, Optional
from pathlib import Path
from dotenv import load_dotenv
from psycopg2.extensions import connection
from psycopg2 import pool

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

logging.basicConfig(level=logging.ERROR)

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
 
def create_insert_query(table : str, columns : Sequence[str]) -> str:
    """

    create a query to insert one or many parameters
    """
    columns_str = f"({', '.join(columns)})"
    placeholders = ", ".join(["%s"] * len(columns))
    query = f"INSERT INTO {table} {columns_str} VALUES ({placeholders})"
    print('this is a query:', query)
    return query


def execute_query(
    connection: connection, query: str, values : Sequence[tuple[Any]], fetch: bool = False
) -> Optional[list[Any]]:
    """
    Execute an SQL query with optional parameters.
    
    Parameters:
    - connection: Active PostgreSQL connection
    - query: SQL query string
    - values: Tuple of query parameters (default: None)
    - fetch: If True, returns query results (for SELECT queries)
    
    Returns:
    - List of results for SELECT queries, None otherwise.
    """
    try:
        with connection.cursor() as cursor:
            cursor.executemany(query, values)
            if fetch:  
                return cursor.fetchall()  # Fetch results only for SELECT queries
            connection.commit()  # Commit for INSERT, UPDATE, DELETE
    except Exception as e:
        connection.rollback()  # Rollback on failure
        logging.error(f"Database error: {e}")
        raise  # Re-raise the exception for better debugging

    return None


cursorDep = Annotated[connection, Depends(get_connection)]