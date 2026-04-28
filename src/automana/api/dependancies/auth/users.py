from typing import Annotated, NoReturn, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from automana.api.dependancies.general import ipDep
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.user_management.user import UserInDB
from automana.api.services.auth.auth import decode_access_token
from automana.core.exceptions import session_exceptions
from automana.core.settings import get_settings

import logging

logger = logging.getLogger(__name__)

LOGIN_URL = "/login"

# auto_error=False: the function handles its own 401s; this declaration
# exists solely so FastAPI emits an OAuth2 security scheme in OpenAPI,
# enabling the Swagger UI padlock.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/auth/token", auto_error=False)


class BrowserAuthRequired(Exception):
    pass


def _raise_auth_error(request: Request, detail: str) -> NoReturn:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        raise BrowserAuthRequired()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_active_user(
    request: Request,
    ip_address: ipDep,
    service_manager: ServiceManagerDep,
    session_cookie: Optional[str] = Cookie(None, alias="session_id"),
    _token: Optional[str] = Depends(_oauth2_scheme),
) -> UserInDB:
    user_agent = request.headers.get("User-Agent", "")
    # session_cookie holds the value of the 'session_id' cookie (alias keeps
    # the cookie name intact while avoiding a name clash with /{session_id}
    # path parameters in routes that use this dependency).
    session_id = session_cookie

    # --- Cookie path ---
    if session_id:
        try:
            user = await service_manager.execute_service(
                "auth.session.get_user_from_session",
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            if not user:
                _raise_auth_error(request, "Invalid session")
            validated = UserInDB.model_validate(user)
            if validated.disabled:
                _raise_auth_error(request, "Account is disabled")
            return validated
        except session_exceptions.SessionError:
            _raise_auth_error(request, "Invalid or expired session")

    # --- Bearer path ---
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        settings = get_settings()
        try:
            payload = decode_access_token(token, settings.jwt_secret_key, settings.jwt_algorithm)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
            )
        user = await service_manager.execute_service(
            "user_management.user.get_by_username",
            username=username,
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        if user.disabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is disabled",
            )
        return user

    # --- No credentials ---
    _raise_auth_error(request, "Not authenticated")


CurrentUserDep = Annotated[UserInDB, Depends(get_current_active_user)]


async def require_admin(
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
) -> UserInDB:
    is_admin_user = await service_manager.execute_service(
        "user_management.role.is_admin",
        user=current_user,
    )
    if not is_admin_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


AdminUserDep = Annotated[UserInDB, Depends(require_admin)]
