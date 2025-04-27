from fastapi import APIRouter, HTTPException, Request, Depends
from typing import List, Annotated
from backend.dependancies import cursorDep, ipDep
from psycopg2.extensions import connection
from backend.models.users import AdminReturnSession
from uuid import UUID

#from backend.utilis import extract_ip
from backend.authentification import get_current_active_user
from backend.database.database_utilis import create_select_query, execute_select_query, create_update_query, execute_queries
from backend.models.users import UserInDB
import psycopg2

session_router = APIRouter(
    prefix='/session',
    tags=['admin-sessions']
)


@session_router.get('/', response_model=List[AdminReturnSession])
async def get_sessions(conn: cursorDep):
    query = create_select_query('active_sessions_view')
    try:
        rows = execute_select_query(conn, query,(None,))
        return rows
    except Exception:
        raise

@session_router.get('/{session_id}/', response_model= AdminReturnSession)
async def get_sessions(conn: cursorDep, session_id : UUID):
    query = create_select_query('active_sessions_view', conditions_list=[('session_id = %s ')])
    try:
        rows = execute_select_query(conn, query, (str(session_id),), select_all=False)
        return rows
    except Exception:
        raise

@session_router.delete('/{session_id}/desactivate')
async def delete_session(conn : cursorDep, ip_address : ipDep, current_user : Annotated[ UserInDB, Depends(get_current_active_user)], request : Request, session_id : UUID):
    query="SELECT inactivate_session(%s, %s, %s);"
    user = current_user.unique_id
    try:
        with conn.cursor() as cursor:
            execute_queries(cursor, query,(str(session_id),user, ip_address,))
            conn.commit()
    except psycopg2.Error as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

