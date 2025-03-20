import logging, os
from psycopg2.extras import RealDictCursor
from fastapi import Depends, HTTPException
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
    return query


def create_select_query(
    table: str, 
    columns: Sequence[str] | None=None, 
    where_columns: Optional[Sequence[str]] = None, 
    order_by: Optional[str] = None, 
    limit: Optional[int] = None
) -> str:
    """
    Generates a SELECT SQL query dynamically.
    
    :param table: Name of the table.
    :param columns: List of column names to retrieve.
    :param where_columns: Optional list of column names to filter with WHERE conditions.
    :param order_by: Optional column name to sort by.
    :param limit: Optional integer to limit results.
    :return: Generated SQL query as a string.
    """
    columns_str = ", ".join(columns) if columns else "*"
    query = f"SELECT {columns_str} FROM {table}"

    if where_columns:
        conditions = " AND ".join([f"{col} = %s" for col in where_columns])
        query += f" WHERE {conditions}"

    if order_by:
        query += f" ORDER BY {order_by}"

    if limit:
        query += f" LIMIT {limit}"

    return query


def execute_query(
    connection: connection, query: str, values : Sequence[tuple[Any]] | tuple[Any], fetch: bool = False
, execute_many : bool = False) -> Optional[list[Any]]:
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
    print( query, values)
    try:
        with connection.cursor() as cursor:
            if values:
                if execute_many:
                    cursor.executemany(query, values)
                else:
                    cursor.execute(query, values)
       
            if fetch:
                data =cursor.fetchall()
                if not data:  # Check if no results found
                    raise HTTPException(status_code=404, detail="Entry not found")
                return data
            connection.commit()  # Commit for INSERT, UPDATE, DELETE
    except Exception as e:
        connection.rollback()  # Rollback on failure
        logging.error(f"Database error: {e}")
        raise e # Re-raise the exception for better debugging

    return None


