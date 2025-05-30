import  jwt
from uuid import  UUID
from backend.modules.auth.models import  CookiesData
from passlib.context import CryptContext
from fastapi import  HTTPException, status, Request
from datetime import timedelta, datetime, timezone
from fastapi.security import OAuth2PasswordBearer
from fastapi import  HTTPException, status, Request, Security
from backend.dependancies import get_general_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

def parse_insert_add_token_result(raw_result: str):
    raw_result = raw_result.strip('()')
    session_id, token_id = raw_result.split(',')
    return session_id, token_id

def extract_session_id(cookies: CookiesData) -> UUID:
    session_id = cookies.session_id
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session_id in cookies",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session_id

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
    encoded_jwt = jwt.encode(to_encode, get_general_settings().secret_key , get_general_settings().encrypt_algorithm )
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
        payload =  jwt.decode(token,key=get_general_settings().secret_key ,algorithms=get_general_settings().encrypt_algorithm)
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


async def check_token_validity(request : Request):
    print('cheking validity')
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
  
