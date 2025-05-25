
from fastapi import Depends, HTTPException, status
from typing_extensions import Annotated
from backend.routers.users.models import UserInDB
from backend.routers.auth.utils import get_token_from_header_or_cookie, decode_access_token
from backend.database.get_database import cursorDep
from backend.database.database_utilis import execute_select_query
from uuid import UUID
from psycopg2.extensions import connection 

def validate_session (conn : connection, session_id : UUID):
    query = "SELECT * FROM active_sessions_view WHERE session_id = %s"
    try:
        row = execute_select_query(conn, query, (session_id,), select_all=False)
        if row:
            return row
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
async def get_current_session(
        conn : cursorDep,
        token: Annotated[str, Depends(get_token_from_header_or_cookie)]
)-> UUID:
    session_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid Token",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = decode_access_token(token)
        session_id =payload.get('session_id')
        if not session_id and not validate_session(conn, session_id):
            raise session_exception
    
        return  UUID(session_id)
    except Exception as e:
        raise session_exception


async def get_current_user(
    conn: cursorDep,
    session_id: Annotated[UUID, Depends(get_current_session)]
) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
   
    # Avoid importing from routers.auth.services here!
    query = """
     WITH
     get_user_id AS (
     SELECT user_id FROM active_sessions_view WHERE session_id = %s
        )
      SELECT * FROM users WHERE unique_id = (SELECT user_id FROM get_user_id);
    """
    try:
        user_data = execute_select_query(conn, query, (session_id,), select_all=False)
        if user_data:
            return UserInDB(**user_data)
    except Exception:
        raise
    raise credentials_exception

# Used by routes that require the user to be active
async def get_current_active_user(
    current_user: UserInDB = Depends(get_current_user)
) -> UserInDB:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_access_ebay_token():
    #get the ebay access token, store it in db
    # if expires or not, check if refresh_token
    # exange refresh token
    #return access token
    
# Aliases for convenient annotation reuse
currentActiveUser = Annotated[UserInDB, Depends(get_current_active_user)]
tokenDep = Annotated[str, Depends(get_token_from_header_or_cookie)]
currentActiveSession = Annotated[UUID, Depends(get_current_session)]