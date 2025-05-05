import os, jwt
from datetime import datetime
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status, Request, Security
from passlib.context import CryptContext
from psycopg2.extensions import connection
from backend.database.database_utilis import execute_select_query, execute_insert_query
from backend.dependancies import cursorDep
from backend.models.users import UserInDB, CreateSession
from typing import Annotated



load_dotenv()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")



def verify_password(plain_password, hashed_password):
    """
    Verifies a plaintext password against a hashed password.

    Args:
        plain_password (str): The raw user-entered password.
        hashed_password (str): The stored bcrypt-hashed password.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_hash_password(password: str):
    """
    Hashes a plain password using bcrypt.

    Args:
        password (str): Plaintext password.

    Returns:
        str: Hashed password.
    """
    return pwd_context.hash(password)



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
    if not verify_password(password, user.hashed_password):
        return False
    return user
    

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """
    Creates a JWT access token.

    Args:
        data (dict): Payload to encode in the token.
        expires_delta (timedelta, optional): Token expiration window. Defaults to 15 mins.

    Returns:
        str: Encoded JWT.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv('SECRET_KEY'), os.getenv('ENCRYPT_ALGORITHM'))
    return encoded_jwt

def decode_access_token(token : str) ->dict:
    """
    Decodes a JWT access token and validates its signature and expiration.

    Args:
        token (str): JWT token string.

    Returns:
        dict: Decoded payload.

    Raises:
        Exception: If the token is expired or invalid.
    """
    try:
        payload =  jwt.decode(token, os.getenv('SECRET_KEY'), algorithms=[os.getenv('ENCRYPT_ALGORITHM')])
        return payload
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")


async def get_token_from_header_or_cookie(request: Request, token: str = Security(oauth2_scheme)) -> str:
    """
    Retrieves the access token from header or cookie.

    Args:
        request (Request): FastAPI request object.
        token (str): Auto-extracted token via OAuth2 scheme.

    Returns:
        str: Access token string.

    Raises:
        HTTPException: If no token is found.
    """
    if token:
        return token
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    raise HTTPException(status_code=401, detail="Token not found")

async def get_current_user( conn : cursorDep, token : str = Depends(get_token_from_header_or_cookie))-> UserInDB :
    """
    Gets the currently authenticated user from the JWT token.

    Args:
        conn (connection): PostgreSQL connection.
        token (str): JWT token.

    Returns:
        UserInDB: Authenticated user.

    Raises:
        HTTPException: If credentials are invalid or user is not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
   
    try:
        payload = decode_access_token(token)
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    
    user = get_user(conn, username=username)
    if not user:
        raise credentials_exception
    return user


async def get_current_active_user(
    
#modify here to not return all the info in the db, maybe only userID
    current_user: UserInDB = Depends(get_current_user))-> UserInDB:
    """
    Ensures the current user is active (not disabled).

    Args:
        current_user (UserInDB): The user extracted from JWT.

    Returns:
        UserInDB: Active user.

    Raises:
        HTTPException: If the user is disabled.
    """
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def check_token_validity(request : Request):
    token = None
    auth = request.headers.get("Authorization")

    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]

    elif 'access_token' in request.cookies:
        token = request.cookies.get('access_token')
    if not token:
        raise HTTPException(status_code=401, detail='No Token')
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=400, detail="Token invalid")
  

def has_role_permission(permission : str):
    """
    Returns a FastAPI dependency that checks if the current user has a specific permission.

    Args:
        permission (str): The required permission name.

    Returns:
        Callable: A dependency function to use in routes.

    Raises:
        HTTPException: If permission is missing or query fails.
    """
    async def checker( user : UserInDB = Depends(get_current_active_user), conn : connection =Depends(cursorDep)):
        query = """ SELECT unique_id FROM user_roles_permission_view WHERE permission = %s AND unique_id = %s """
        try:
            ids = execute_select_query(conn, query, (permission, user.unique_id,), False)
            if ids is None:
                raise HTTPException(status_code=403, detail=f"User lacks '{permission}' permission.")
        except Exception as e:
            raise HTTPException(status_code=500, detail='Error Finding the permission:{e}',)
    return checker()
        

def has_role(role : str):
    """
    Returns a FastAPI dependency that checks if the user has a specific role.

    Args:
        role (str): Role name to verify.

    Returns:
        Callable: A dependency function for FastAPI routes.

    Raises:
        HTTPException: If the role is not found.
    """
    async def checker( conn : cursorDep, user : UserInDB = Depends(get_current_active_user)):
        query = """ SELECT unique_id FROM user_roles_permission_view WHERE role = %s AND unique_id = %s """
        try:
            ids = execute_select_query(conn, query, (role, user.unique_id,), False)
            if ids is None:
                raise HTTPException(status_code=403, detail=f"User lacks '{role}' permission.")
        except Exception as e:
            raise HTTPException(status_code=500, detail='Error Finding the permission:{e}',)
    return checker

currentActiveUser = Annotated[UserInDB, Depends(get_current_active_user)]