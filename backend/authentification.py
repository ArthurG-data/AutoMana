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
from backend.models.users import UserInDB, CreateSession, PublicSession
from backend.models.utils import TokenData



load_dotenv()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_hash_password(password: str):
    return pwd_context.hash(password)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def get_user(conn : connection, username: str)-> UserInDB:
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
    user : UserInDB = get_user(conn, username)
   
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user
    

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv('SECRET_KEY'), os.getenv('ENCRYPT_ALGORITHM'))
    return encoded_jwt

def decode_access_token(token : str) ->dict:
    try:
        payload =  jwt.decode(token, os.getenv('SECRET_KEY'), algorithms=[os.getenv('ENCRYPT_ALGORITHM')])
        return payload
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")


async def get_token_from_header_or_cookie(request: Request, token: str = Security(oauth2_scheme)) -> str:
    if token:
        return token
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    raise HTTPException(status_code=401, detail="Token not found")

async def get_current_user( conn : cursorDep, token : str = Depends(get_token_from_header_or_cookie))-> UserInDB :
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
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def is_admin(
        current_user : UserInDB=Depends(get_current_active_user))->bool:
        return current_user.role == "admin"
        

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
  

