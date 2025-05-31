import logging, os, psycopg2
from fastapi import Depends, HTTPException, Query, Response
from typing import List, Union, Optional, Sequence, Annotated, Callable, Any
from pydantic import BaseModel
from psycopg2.extensions import connection, cursor
from backend.database.get_database import get_cursor
from uuid import UUID
from backend.database import errors
from typing import Tuple, Dict

logging.basicConfig(level=logging.ERROR)

def format_columns(columns: Sequence[str]) -> str:
    return f"({', '.join(columns)})"

def format_placeholders(count: int) -> str:
    return ", ".join(["%s"] * count)

def format_conditions(conditions: Sequence[Union[str, tuple]]) -> str:
    """
    Accepts a mix of strings and (column, 'IN') tuples for dynamic clause formatting.
    example" # Find listings for multiple card IDs
    conditions = [("card_version_id", "IN"), "status = 'active'"]
    query = create_select_query("card_version", ["card_version_id", "oracle_text"], conditions)

    """
    formatted = []
    for cond in conditions:
        if isinstance(cond, tuple) and cond[1].upper() == "IN":
            column = cond[0]
            formatted.append(f"{column} = ANY(%s)")  # PostgreSQL idiomatic IN
        else:
            formatted.append(cond)
    return " AND ".join(formatted)

def create_insert_query(table: str,
    data: Dict[str, Union[str, int, float]],
    returning: Optional[str] = None
) -> Tuple[str, List]:
    columns = data.keys()
    if not columns:
        raise errors.QueryCreationError("Cannot build INSERT with no columns to insert")
    values = list(data.values())
    if len(columns) != len(values):
        raise errors.QueryCreationError("Missing values for the parameters")
    placeholders = ", ".join(["%s"] * len(columns))
    column_str = ", ".join(columns)
    query = f"INSERT INTO {table} ({column_str}) VALUES ({placeholders})"
    if returning:
        query += f" RETURNING {returning}"
    return query, values

def create_delete_query(table: str,
    conditions: Sequence[Tuple[str, str, Union[str, int, float]]]
) -> Tuple[str, List]:
    where_parts = []
    values = []
    for col, op, val in conditions:
        where_parts.append(f"{col} {op} %s")
        values.append(val)

    query = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"
    return query, values

def create_update_query(table: str,
    updates: Dict[str, Union[str, int, float]],
    conditions: Sequence[Tuple[str, str, Union[str, int, float]]]
) -> Tuple[str, List]:
    if not updates:
        raise errors.QueryCreationError("Cannot build UPDATE query with no columns to update.")
    if not conditions:
        raise errors.QueryCreationError("Cannot build UPDATE query without WHERE conditions.")
    set_parts = [f"{col} = %s" for col in updates]
    set_clause = ", ".join(set_parts)
    values = list(updates.values())

    where_parts = []
    for col, op, val in conditions:
        where_parts.append(f"{col} {op} %s")
        values.append(val)

    query = f"UPDATE {table} SET {set_clause} WHERE {' AND '.join(where_parts)}"
    return query, values

def create_select_query(
    table: str, 
    return_columns: Sequence[str] | None=None, 
    conditions: Optional[Sequence[Union[str, Tuple[str, str, Union[str, int, Sequence]]]]] = None,
    limit : Optional[int]= None, 
    offset : Optional[int]= None, 
    order_by: Optional[str] = None, 
) -> Tuple[str, List]:
    """
    Generates a SELECT SQL query dynamically.
    
    :param table: Name of the table.
    :param columns: List of column names to retrieve.
    :param where_columns: Optional list of column names to filter with WHERE conditions.
    :param order_by: Optional column name to sort by.
    :param limit: Optional integer to limit results.
    :return: Generated SQL query as a string.
    """
    if not table:
        raise errors.QueryCreationError("A table name is required for Select Queries")
    
    columns_str = ", ".join(return_columns) if return_columns else "*"
    query = f"SELECT {columns_str} FROM {table}"
    params = []
    if conditions:
        where_parts = []
        for cond in conditions:
            if isinstance(cond, str):
                where_parts.append(cond)
            else:
                col, op, val = cond
                if op.upper() == "IN":
                    where_parts.append(f"{col} = ANY(%s)")
                else:
                    where_parts.append(f"{col} {op} %s")
                params.append(val)
        query += " WHERE " + " AND ".join(where_parts)

    if order_by:
        query += f" ORDER BY {order_by}"
    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)
    if offset is not None:
        query += " OFFSET %s"
        params.append(offset)
    return query, params

  
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
    if execute_many:
        cursor.executemany(query, values)
    else:
        cursor.execute(query, values)
 
   

def execute_delete_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):    
    with get_cursor(connection) as cursor:
        execute_queries(cursor, query, values, execute_many)
        connection.commit()
        return Response(status_code=204)    


def execute_insert_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], return_id : Optional[str]=None, execute_many = False):
    with get_cursor(connection) as cursor:
        execute_queries(cursor, query, values, execute_many)
        connection.commit()
        if return_id:
            try:
                rows = cursor.fetchall()
                inserted_ids = [row[return_id] for row in rows]
                return inserted_ids if execute_many else inserted_ids[0]
            except Exception:
                raise RuntimeError("Expected return_id but function returned nothing")
        else:
            return
  
def execute_select_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False, select_all=True):
    with  connection.cursor() as cursor:
        execute_queries(cursor, query, values, execute_many)
        return cursor.fetchall() if select_all else cursor.fetchone()
    
def execute_update_query(connection : connection, query : str, values : Sequence[tuple[Any]] | tuple[Any], execute_many = False):
    with connection.cursor() as cursor:
        execute_queries(cursor, query, values, execute_many)
        connection.commit()
        return Response(status_code=204)


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
