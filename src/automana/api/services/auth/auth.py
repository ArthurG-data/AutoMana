import jwt
import bcrypt
from datetime import datetime, timedelta, timezone

# Password utilities

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a hashed password."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_hash_password(password: str) -> str:
    """Hashes a plain password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

# JWT utilities 
def create_access_token(data: dict, secret_key: str, algorithm: str, expires_delta: timedelta = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode
                      , secret_key
                      , algorithm)

def decode_access_token(token: str, secret_key: str, algorithm: str) -> dict:
    """Decodes a JWT token and validates its signature."""
    try:
        return jwt.decode(token, key=secret_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
