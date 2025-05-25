import os

from datetime import timedelta,datetime, timezone
from uuid import UUID, uuid4
from backend.utilis import now_utc

from fastapi import HTTPException, status,  Request, Response
from psycopg2.extensions import connection

from backend.routers.auth.models import CookiesData, CreateSession, Token
from backend.routers.auth import  utils
from backend.routers.users.models import UserInDB
from backend.database.database_utilis import (
    execute_insert_query,
    execute_select_query
)
from fastapi.security import OAuth2PasswordRequestForm
from backend.shared.dependancies import get_current_user
from backend.dependancies import get_general_settings
from backend.routers.auth import queries

def insert_session(conn : connection, new_session : CreateSession):
     #create the session
    query = """   SELECT insert_add_token(%s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    values = (new_session.session_id, str(new_session.user_id), new_session.created_at, new_session.expires_at, new_session.ip_address, new_session.user_agent, new_session.refresh_token, new_session.refresh_token_expires_at, new_session.device_id,)
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values)
            result = cursor.fetchone()
        
            conn.commit()
            raw_result = result['insert_add_token']
            return utils.parse_insert_add_token_result(raw_result)
    except Exception: 
        conn.rollback()
        raise
def get_active_session(conn : connection, user_id: UUID):
    with conn.cursor() as cursor:
        cursor.execute("SELECT session_id, token_id FROM active_sessions_view WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        return result 

def handle_session_rotation_or_creation(conn : connection, user , ip_address, user_agent, session_info, expire_time):
    if session_info:
        session_id = session_info.get('session_id')
        token_id = session_info.get('token_id')
        refresh_token = utils.create_access_token(data={"session_id": str(session_id)}, expires_delta=timedelta(days=7))
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT rotate_refresh_token(%s, %s, %s, %s);',
                (token_id, session_id, refresh_token, expire_time)
            )
            conn.commit()
        return session_id, refresh_token
    else:
        session_id = uuid4()
        refresh_token = utils.create_access_token(data={"session_id": str(session_id)}, expires_delta=timedelta(days=7))
        new_session = CreateSession(
            user_id=user.unique_id,
            ip_address=ip_address,
            refresh_token=refresh_token,
            refresh_token_expires_at=expire_time,
            user_agent=user_agent
        )
       
        session_id, _ = insert_session(conn, new_session)
        return session_id, refresh_token
    

def fetch_session_row(conn: connection, session_id: UUID, ip_address: str, user_agent: str) -> dict:
    query = """
    SELECT refresh_token
    FROM active_sessions_view
    WHERE session_id = %s AND user_agent = %s AND ip_address = %s;
    """
    result = execute_select_query(conn, query, (session_id, user_agent, ip_address), select_all=False)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return result

def validate_cookie(cookies: CookiesData, conn: connection):
    session_id = utils.extract_session_id(cookies)
    ip_address = cookies.ip_address
    user_agent = cookies.user_agent

    try:
        session_data = fetch_session_row(conn, session_id, ip_address, user_agent)
        return session_data
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server error validating token",
        )
   

def get_user(conn: connection, username: str) -> UserInDB:
    """
    Fetches a user from the database by username.

    Args:
        conn (connection): PostgreSQL connection object.
        username (str): The username to search for.

    Returns:
        UserInDB: User model if found, else None.

    Raises:
        Exception: If the query fails.
    """
    query = "SELECT * FROM users WHERE username = %s"
    try:
        user = execute_select_query(conn,query, (username,), select_all=False)
        if user:
            return UserInDB(**user)
    except Exception:
        raise 
   
def create_session(conn: connection, new_session : CreateSession):
    query = "INSERT INTO sessions (user_id, created_at, expires_at,refresh_token,refresh_token_expires_at, ip_address, user_agent) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id"
    try:
        return execute_insert_query(query, new_session.model_dump())
    except Exception:
        raise

def authenticate_user(conn : connection, username : str, password : str):
    """
    Verifies user credentials against stored records.

    Args:
        conn (connection): PostgreSQL connection.
        username (str): Username of the user.
        password (str): Plaintext password.

    Returns:
        UserInDB | bool: Returns user object if authenticated, False otherwise.
    """
    user : UserInDB = get_user(conn, username)
   
    if not user:
        return False
    if not utils.verify_password(password, user.hashed_password):
        return False
    return user
        
def validate_credentials(conn, username: str, password: str):
    user = authenticate_user(conn, username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def login(conn : connection ,  ip_address : str, response : Response, request: Request, form_data: OAuth2PasswordRequestForm) -> Token:

    access_token_expires = timedelta(minutes=int(get_general_settings().access_token_expiry))
    user_agent = request.headers.get('user-agent')
    expire_time = datetime.now(timezone.utc) +  timedelta(days=7)
    try:
        user = validate_credentials(conn, form_data.username, form_data.password)
        session_info = get_active_session(conn, user.unique_id)
        session_id, refresh_token = handle_session_rotation_or_creation(conn, user, ip_address, user_agent, session_info, expire_time)
        access_token = utils.create_access_token(
            data={"session_id": str(session_id)},
            expires_delta=access_token_expires
        )

        response.set_cookie(
            key="session_id",
            value=str(session_id),
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=60*60*24*7,
        )

        return Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

async def read_cookie( conn : connection, ip_address : str ,response : Response, request: Request):
    session_id = request.cookies.get('session_id')
    user_agent = request.headers.get('user-agent')
    expires_on = request.cookies.get('exp')
    cookie = CookiesData(session_id=session_id, ip_address=ip_address, user_agent=user_agent, expires_on=expires_on)
    refresh_token = validate_cookie(cookie, conn,).get('refresh_token')
    if not refresh_token:
        raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token Invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # get the corresponding token from the db and check user
    user : UserInDB =  await get_current_user(conn, token=refresh_token)

    if not user.disabled:
        access_token_expires = timedelta(minutes=int(get_general_settings().access_token_expiry))
        access_token = utils.create_access_token( data={"sub": user.username, "id" : str(user.unique_id), "role":user.role},expires_delta=access_token_expires)
        refresh_expiry = now_utc() + timedelta(days=7)
        refresh_token = utils.create_access_token(
            data={"sub": user.username, "id" : str(user.unique_id), "role":user.role}, expires_delta=timedelta(days=7)
        )
        #remove the old refresh token from cookie
        response.delete_cookie('refresh_token_id')
        
        query = """ SELECT rotate_refresh_token(%s, %s, %s, %s); """
        values = (token_id, session_id, refresh_token, refresh_expiry,)
        try:
            token_id = execute_select_query(conn, query, values, select_all=False)
            response.set_cookie(
                key="refresh_token_id",
                value=str(token_id),
                httponly=True,
                secure=True,
                samesite="strict",
                max_age=60*60*24*7,
            )
        except Exception:
            raise
        #add the token_id to the cookie
        return Token(access_token=access_token, token_type="bearer")
   
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token Invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )

async def get_info_session(conn: connection, session_id :UUID)->UUID:
    try:
        row = execute_select_query(conn, queries.get_info_session_query, (str(session_id),), select_all=False)
        if row:
            return row
        else:
            raise HTTPException(status_code=401, detail="No sessions files")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{e}")
        