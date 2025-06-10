from fastapi import Request
from fastapi.responses import JSONResponse
from backend.modules.auth.errors import  (
    AuthError, InvalidCredentialsError,
    SessionNotFoundError, TokenExpiredError,
    SessionCreationError, TokenRotationError
)
import logging

logger = logging.getLogger("auth")

async def auth_error_handler(request: Request, exc: AuthError):
    logger.warning(f"[AUTH ERROR] {exc}", exc_info=True)

    if isinstance(exc, InvalidCredentialsError):
        return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})

    if isinstance(exc, TokenExpiredError):
        return JSONResponse(status_code=401, content={"detail": "Token expired"})

    if isinstance(exc, SessionNotFoundError):
        return JSONResponse(status_code=401, content={"detail": "Session not found or invalid"})

    if isinstance(exc, SessionCreationError):
        return JSONResponse(status_code=500, content={"detail": "Failed to create session"})

    if isinstance(exc, TokenRotationError):
        return JSONResponse(status_code=500, content={"detail": "Failed to rotate refresh token"})

    return JSONResponse(status_code=400, content={"detail": str(exc)})