import logging, os, psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import Depends, HTTPException
from typing import Annotated, Any, Sequence,Generator, Optional
from pathlib import Path
from dotenv import load_dotenv
from psycopg2.extensions import connection, cursor
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

def create_delete_query(table : str, conditions : Sequence[str]) -> str:
    condition_string = " AND ".join(conditions)
    condition_string = "WHERE " + condition_string
    query = f" DELETE FROM {table} {condition_string}; "
    return query

def create_update_query(table : str, updates : Sequence[str], conditions : Sequence[str]) -> str:

    update_string = ', '.join([f'{update} = %s'for update in updates])
    condition_string = ' AND'.join(conditions)
    query = f'UPDATE {table} SET {update_string} WHERE {condition_string}'
    return query

def create_select_query(
    table: str, 
    return_columns: Sequence[str] | None=None, 
    conditions_list: Optional[Sequence[str]] = None, 
    order_by: Optional[str] = None, 
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
    columns_str = ", ".join(return_columns) if return_columns else "*"
    query = f"SELECT {columns_str} FROM {table}"

    if conditions_list:
        conditions = " AND ".join([f"{condition}" for condition in conditions_list])
        query += f" WHERE {conditions}"

    if order_by:
        query += f" ORDER BY {order_by}"

    
    query += f" LIMIT %s "
    
    query += f" OFFSET %s "

    return query


def get_cursor(connection : connection) -> cursor:
    pointer = connection.cursor()
    try:
        return pointer
    except Exception as e:
        raise
  
def exception_handler(exception: Exception):
    """Handles database exceptions and raises appropriate HTTP responses."""
    if isinstance(exception, psycopg2.IntegrityError):  # Unique constraint or foreign key issues
        raise HTTPException(status_code=409, detail="Conflict: Duplicate entry or constraint violation.")
    
    elif isinstance(exception, psycopg2.OperationalError):  # Connection issues
        raise HTTPException(status_code=500, detail="Database connection error.")
    
    elif isinstance(exception, psycopg2.DataError):  # Invalid data format
        raise HTTPException(status_code=400, detail="Invalid data provided.")
    
    elif isinstance(exception, psycopg2.ProgrammingError):  # Query syntax errors
        raise HTTPException(status_code=400, detail="Invalid SQL query.")
    
    elif isinstance(exception, psycopg2.DatabaseError):  # Generic database errors
        logging.error(f"Database error: {exception}")
        raise HTTPException(status_code=500, detail="Internal server error.")
    
    else:  # Other unexpected errors
        logging.error(f"Unexpected error: {exception}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
    

def execute_queries(cursor : cursor, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):
    try:
        if execute_many:
            cursor.executemany(query, values)
        else:
            print(query, values)
            cursor.execute(query, values)
        cursor.connection.commit()
    except Exception as e:
        cursor.connection.rollback()
        exception_handler(e)
 

def execute_delete_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):
    try:
        with get_cursor(connection) as cursor:
            execute_queries(cursor, query, values, execute_many)
            connection.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not found")
    except Exception:
        raise

def execute_insert_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):
    try:
        with get_cursor(connection) as cursor:
            execute_queries(cursor, query, values, execute_many)
            rows = cursor.fetchall()
            inserted_ids = [row['unique_id'] for row in rows] 

        return inserted_ids if execute_many else inserted_ids[0]
    except Exception:
        raise
def execute_select_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):
    try:
        with get_cursor(connection) as cursor:
            execute_queries(cursor, query, values, execute_many)
            rows = cursor.fetchall()
        return rows
    except Exception:
        raise

def execute_update_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):
    try:
        with get_cursor(connection) as cursor:
            execute_queries(cursor, query, values, execute_many)
            
    except Exception:
        raise

def execute_query(
    connection: connection, query: str, values : Sequence[tuple[Any]] | tuple[Any], fetch: bool = False, execute_many : bool = False) -> Optional[list[Any]]:
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


