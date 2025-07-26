import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone

# Password utilities
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_hash_password(password: str) -> str:
    """Hashes a plain password using bcrypt."""
    return pwd_context.hash(password)

# JWT utilities 
def create_access_token(data: dict, secret_key: str, algorithm: str, expires_delta: timedelta = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm)

def decode_access_token(token: str, secret_key: str, algorithm: str) -> dict:
    """Decodes a JWT token and validates its signature."""
    try:
        return jwt.decode(token, key=secret_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

# Simple data parsing
def parse_insert_add_token_result(raw_result: str):
    """Parse database result for token insertion."""
    raw_result = raw_result.strip('()')
    session_id, token_id = raw_result.split(',')
    return session_id, token_id
