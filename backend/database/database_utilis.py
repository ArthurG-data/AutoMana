import logging, os, psycopg2
from fastapi import Depends, HTTPException, Query, Response
from typing import List, Union, Optional, Sequence, Annotated, Callable, Any
from pydantic import BaseModel
from psycopg2.extensions import connection, cursor
from backend.database.get_database import get_cursor
from uuid import UUID


logging.basicConfig(level=logging.ERROR)



def create_insert_query(table : str, columns : Sequence[str], column_id : str) -> str:
    """

    create a query to insert one or many parameters
    """
    columns_str = f"({', '.join(columns)})"
    placeholders = ", ".join(["%s"] * len(columns))
    query = f"INSERT INTO {table} {columns_str} VALUES ({placeholders}) RETURNING {column_id} "
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
    limit : Optional[int]= None, 
    offset : Optional[int]= None, 
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

    if limit:
        query += f" LIMIT %s "
    if offset is not None:
        query += f" OFFSET %s "

    return query

  
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
            return Response(status_code=204)    
    except Exception:
        raise

def execute_insert_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], unique_id = 'unique_id', execute_many = False):
    try:
        with get_cursor(connection) as cursor:
            execute_queries(cursor, query, values, execute_many)
            rows = cursor.fetchall()
            print(rows)
            inserted_ids = [row[unique_id] for row in rows] 

        return inserted_ids if execute_many else inserted_ids[0]
    except Exception:
        raise
def execute_select_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False, select_all=True):
    try:
        with get_cursor(connection) as cursor:
            execute_queries(cursor, query, values, execute_many)
            if select_all:
                rows = cursor.fetchall()
            else:
                rows = cursor.fetchone()
        return rows
    except Exception:
        raise

def execute_update_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):
    try:
        with get_cursor(connection) as cursor:
            execute_queries(cursor, query, values, execute_many)
            return Response(status_code=204)
            
    except Exception:
        connection
        raise


def create_value(values, is_list, limit, offset):
    if is_list:
        values = ((values ), limit , offset)
    elif values:
        values = (values ,)
    else:
        values = (limit , offset)
    return values

def get_rows(connection : connection,
            query_creator_function : Callable[[bool, Optional[Union[Sequence[str], str]]], str],
            values: Optional[str|Sequence[str]]=None,  
            limit : Annotated[int, Query(le=100)]=100,
            offset: int = 0,
            select_all : bool = True ) -> Union[BaseModel|List[BaseModel]]:
    is_list = isinstance(values, list)  
    query = query_creator_function(is_list, values)
    values = create_value(values, is_list, limit, offset)
    
    try:
        rows = execute_select_query(connection, query, values, execute_many=False, select_all=select_all)
        return rows
    except Exception:
        raise

def delete_rows(connection : connection,
                query_creator_function : Callable,
                values: Optional[str|Sequence[str]]=None,
                ):
    is_list = isinstance(values, list)
   
    query = query_creator_function(is_list, values)
    print(query)
    try:
        execute_delete_query(connection, query, values, execute_many=False)
        return Response(status_code=204)
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
