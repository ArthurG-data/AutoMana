
from fastapi import Depends, HTTPException, status
from typing_extensions import Annotated
from backend.routers.users.models import UserInDB
from backend.routers.auth.utils import get_token_from_header_or_cookie, decode_access_token
from backend.database.get_database import cursorDep
from backend.database.database_utilis import execute_select_query



async def get_current_user(
    conn: cursorDep,
    token: Annotated[str, Depends(get_token_from_header_or_cookie)]
) -> UserInDB:
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

    # Avoid importing from routers.auth.services here!
    query = "SELECT * FROM users WHERE username = %s"
    try:
        user_data = execute_select_query(conn, query, (username,), select_all=False)
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

# Aliases for convenient annotation reuse
currentActiveUser = Annotated[UserInDB, Depends(get_current_active_user)]
tokenDep = Annotated[str, Depends(get_token_from_header_or_cookie)]