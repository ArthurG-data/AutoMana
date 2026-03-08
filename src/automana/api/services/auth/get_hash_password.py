from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_hash_password(password: str):
    """
    Hashes a plain password using bcrypt.

    Args:
        password (str): Plaintext password.

    Returns:
        str: Hashed password.
    """
    return pwd_context.hash(password)
