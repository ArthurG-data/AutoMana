from typing import Annotated, NoReturn, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status

from automana.api.dependancies.general import ipDep
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.user_management.user import UserInDB
from automana.api.services.auth.auth import decode_access_token
from automana.core.exceptions import session_exceptions
from automana.core.settings import get_settings

import logging

logger = logging.getLogger(__name__)

LOGIN_URL = "/login"


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
    session_id: Optional[str] = Cookie(None),
) -> UserInDB:
    user_agent = request.headers.get("User-Agent", "")

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
            return UserInDB.model_validate(user)
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
        return user

    # --- No credentials ---
    _raise_auth_error(request, "Not authenticated")


CurrentUserDep = Annotated[UserInDB, Depends(get_current_active_user)]
