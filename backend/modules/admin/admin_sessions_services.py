from fastapi import  HTTPException, Request
from backend.dependancies import ipDep
from psycopg2.extensions import connection
from uuid import UUID

#from backend.utilis import extract_ip
from backend.modules.auth.dependancies import currentActiveUser
from backend.database.database_utilis import create_select_query, execute_select_query, create_update_query, execute_queries
import psycopg2

async def get_sessions(conn: connection):
    query = create_select_query('active_sessions_view')
    try:
        rows = execute_select_query(conn, query,(None,))
        return rows
    except Exception:
        raise

async def get_sessions(conn: connection, session_id : UUID):
    query = create_select_query('active_sessions_view', conditions_list=[('session_id = %s ')])
    try:
        rows = execute_select_query(conn, query, (str(session_id),), select_all=False)
        return rows
    except Exception:
        raise

async def delete_session(conn : connection, ip_address : ipDep, current_user : currentActiveUser, request : Request, session_id : UUID):
    query="SELECT inactivate_session(%s, %s, %s);"
    user = current_user.unique_id
    try:
        with conn.cursor() as cursor:
            execute_queries(cursor, query,(str(session_id),user, ip_address,))
            conn.commit()
    except psycopg2.Error as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

