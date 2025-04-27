import os
from fastapi import APIRouter, Response, Depends, HTTPException, status, Request
from datetime import timedelta, datetime, timezone
from backend.authentification import authenticate_user, create_access_token, decode_access_token, get_token_from_header_or_cookie, get_current_user
from typing import Annotated
from backend.dependancies import cursorDep, ipDep
from fastapi.security import OAuth2PasswordRequestForm
from backend.models.utils import Token, CookiesData
from backend.models.users import CreateSession, UserInDB
from backend.database.database_utilis import create_insert_query, execute_insert_query, execute_select_query
from psycopg2.extensions import connection


authentification_router = APIRouter(
    prefix='/auth',
    tags=['authentificate'])


def parse_insert_add_token_result(raw_result: str):
    raw_result = raw_result.strip('()')
    session_id, token_id = raw_result.split(',')
    return session_id, token_id

def insert_session(conn : connection, new_session : CreateSession):
     #create the session
    query = """   SELECT insert_add_token(%s, %s, %s, %s, %s, %s, %s, %s);
    """
    values = (str(new_session.user_id), new_session.created_at, new_session.expires_at, new_session.ip_address, new_session.user_agent, new_session.refresh_token, new_session.refresh_token_expires_at, new_session.device_id,)
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values)
            result = cursor.fetchone()
        
            conn.commit()
            raw_result = result['insert_add_token']
            return parse_insert_add_token_result(raw_result)
    except Exception: 
        conn.rollback()
        raise

@authentification_router.post('/token', description='Using an authorization form, authentificate a user against the database and return a bearer token and a cookie with a refresh token')
async def login(conn : cursorDep ,  ip_address : ipDep, response : Response, request: Request, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    try:
        user = authenticate_user(conn, form_data.username, form_data.password)
    
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=int(os.getenv('ACCESS_TOKEN_EXPIRY')))
        access_token = create_access_token(
            data={"sub": user.username, "id" : str(user.unique_id), "role":user.role},expires_delta=access_token_expires
        )
        refresh_token = create_access_token(
                data={"sub": user.username, "id" : str(user.unique_id), "role":user.role}, expires_delta=timedelta(days=7)
        )
        #now in a transaction
        user_agent = request.headers.get('user-agent')
        expire_time = datetime.now(timezone.utc) +  timedelta(days=7)
        new_session = CreateSession(user_id= user.unique_id, ip_address=ip_address, refresh_token=refresh_token, refresh_token_expires_at=expire_time,  user_agent=user_agent)
        
        session_id, token_id = insert_session(conn, new_session)

        response.set_cookie(
            key="refresh_token_id",
            value=str(token_id),
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=60*60*24*7,
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
    except Exception: 
        raise

@authentification_router.post('/session', description='create a session for a user, add an entry to the DB')
async def add_session(  conn : cursorDep, request: Request, token : str = Depends(get_token_from_header_or_cookie)):
    decoded_token = decode_access_token(token)
    ip = extract_ip(request)
    id = decoded_token.get('id')
    new_session = CreateSession(id, ip_address=ip,)
    return new_session

def validate_cookie(cookies : CookiesData, conn: connection, user_id : str):
    '''
    from the cookie, validate the informations
    '''
    session_id = cookies.session_id
    token_id = cookies.refresh_token_id
    if not session_id or not token_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session or token ID in cookies",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    query = """
    SELECT refresh_token
    FROM refresh_tokens
    WHERE token_id = %s AND session_id = %s
    """
    try:
        row = execute_select_query(conn, query, (session_id, token_id,), select_all=False)
        if not row:
            raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        return row
    except Exception as e:
        # You can optionally log the error here
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server error validating token",
        )
    

@authentification_router.get('/exange-cookie', description='exanges the refresh token in a cookie for a auth token')
async def read_cookie( conn : cursorDep,request: Request):
    session_id = request.cookies.get('session_id')
    token_id = request.cookies.get('refresh_token_id')
    cookie = CookiesData(session_id, token_id)
    refresh_token = validate_cookie(cookie)
    if not refresh_token:
        raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token Invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # get the corresponding token from the db and check user
    user : UserInDB =  await get_current_user(conn, token=refresh_token)

    if not user.disabled:
        access_token_expires = timedelta(minutes=int(os.getenv('ACCESS_TOKEN_EXPIRY')))
        access_token = create_access_token( data={"sub": user.username, "id" : str(user.unique_id), "role":user.role},expires_delta=access_token_expires)
        return Token(access_token=access_token, token_type="bearer")
   
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token Invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )

@authentification_router.post('/logout', status_code=204, description='remove a refresh token')
async def remove_cookie(response : Response):
    response.delete_cookie('refresh_token')
    