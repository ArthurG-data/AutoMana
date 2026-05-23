from fastapi import APIRouter, Response, Depends, HTTPException, Request
from typing import Annotated

from fastapi.responses import JSONResponse
from automana.api.dependancies.general import ipDep
from fastapi.security import OAuth2PasswordRequestForm
from automana.api.schemas.auth.token import Token, TokenResponse
from automana.core.exceptions.session_exceptions import SessionNotFoundError, SessionError
from automana.core.exceptions.service_layer_exceptions.user_management.user_exceptions import InvalidResetTokenError
from automana.api.schemas.auth.password_reset import ForgotPasswordRequest, ResetPasswordRequest
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import ErrorResponse
from automana.core.settings import get_settings
import logging

logger = logging.getLogger(__name__)

authentification_router = APIRouter(
    prefix='/auth',
    tags=['Auth'],
)

_AUTH_ERRORS = {
    422: {"description": "Validation error — missing or malformed request fields"},
    500: {"description": "Internal server error", "model": ErrorResponse},
}


@authentification_router.post(
    '/token',
    summary="Log in and obtain access and refresh tokens",
    description=(
        "Authenticates a user with username/password via an OAuth2 password form. "
        "On success, returns a JSON payload containing `access_token` (use as "
        "`Authorization: Bearer <token>` for API callers) and sets an `httponly` "
        "`session_id` cookie for browser-based clients. "
        "The `secure` cookie flag is enabled in all non-`dev` environments."
    ),
    response_model=TokenResponse,
    response_model_exclude_unset=True,
    status_code=200,
    operation_id="auth_login",
    responses={
        401: {"description": "Invalid credentials"},
        **_AUTH_ERRORS,
    },
)
async def login(
    ip_address: ipDep,
    request: Request,
    service_manager: ServiceManagerDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    result = await service_manager.execute_service(
        "auth.auth.login",
        username=form_data.username,
        password=form_data.password,
        ip_address=ip_address,
        user_agent=request.headers.get("User-Agent"),
    )
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    settings = get_settings()
    token_response = TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        token_type="bearer",
        expires_in=settings.access_token_expiry * 60,
    )
    json_response = JSONResponse(
        content=token_response.model_dump(),
        status_code=200,
    )

    # Secure flag requires HTTPS — dev runs over plain HTTP so the browser
    # would silently drop Secure cookies. All other envs (staging, prod) sit
    # behind the nginx TLS terminator and must have Secure on.
    secure_cookies = get_settings().env != "dev"
    if "session_id" in result:
        json_response.set_cookie(
            key="session_id",
            value=result["session_id"],
            httponly=True,
            secure=secure_cookies,
            samesite="strict",
            max_age=60 * 60 * 24 * 7,
        )
    return json_response


@authentification_router.post(
    '/token/refresh',
    summary="Refresh the access token using the session cookie",
    description=(
        "Exchanges the `session_id` cookie (containing the refresh token) for a "
        "new access token. The cookie must be present and valid. "
        "Returns a new `TokenResponse` with an updated `access_token`."
    ),
    response_model=TokenResponse,
    response_model_exclude_unset=True,
    operation_id="auth_refresh_token",
    responses={
        401: {"description": "Missing or invalid session cookie / refresh token expired"},
        **_AUTH_ERRORS,
    },
)
async def refresh_token(
    ip_address: ipDep,
    request: Request,
    response: Response,
    service_manager: ServiceManagerDep,
):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="No session cookie")
    user_agent = request.headers.get("User-Agent", "")
    try:
        result = await service_manager.execute_service(
            "auth.session.refresh",
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except (SessionNotFoundError, SessionError):
        raise HTTPException(status_code=401, detail="Session invalid or expired")
    token_response = TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        token_type="bearer",
        expires_in=result["expires_in"],
    )
    secure_cookies = get_settings().env != "dev"
    response.set_cookie(
        key="session_id",
        value=result["session_id"],
        httponly=True,
        secure=secure_cookies,
        samesite="strict",
        max_age=60 * 60 * 24 * 7,
    )
    return token_response


@authentification_router.post(
    '/logout',
    summary="Log out and invalidate the current session",
    description=(
        "Clears the `session_id` cookie and marks the session as inactive in the "
        "database. If no session cookie is present the endpoint still returns 204 "
        "(idempotent). Errors during server-side invalidation are logged but do not "
        "prevent the cookie from being cleared."
    ),
    status_code=204,
    operation_id="auth_logout",
    responses={
        204: {"description": "Session cleared successfully (or no active session found)"},
        **_AUTH_ERRORS,
    },
)
async def logout(
    ip_address: ipDep,
    response: Response,
    request: Request,
    service_manager: ServiceManagerDep,
):
    session_id = request.cookies.get("session_id")
    if session_id:
        returned = await service_manager.execute_service(
            'auth.auth.logout',
            session_id=session_id,
            ip_address=ip_address,
        )
        if returned.get("status") == "error":
            logger.warning(
                "logout_failed",
                extra={"session_id": session_id, "reason": returned.get("message")},
            )
    response.delete_cookie('session_id')
    return None


@authentification_router.post(
    '/forgot-password',
    summary="Request a password reset link",
    description=(
        "Accepts an email address and sends a reset link if the email is registered. "
        "Always returns 200 to prevent user enumeration."
    ),
    status_code=200,
    operation_id="auth_forgot_password",
    responses={**_AUTH_ERRORS},
)
async def forgot_password(
    body: ForgotPasswordRequest,
    service_manager: ServiceManagerDep,
):
    await service_manager.execute_service(
        "auth.password.request_reset",
        email=body.email,
    )
    return {"message": "If that email exists, a reset link has been sent."}


@authentification_router.post(
    '/reset-password',
    summary="Reset password using a token from the reset email",
    description=(
        "Validates the one-time reset token, updates the user's password, "
        "and invalidates all active sessions. Returns 400 if the token is "
        "invalid, expired, or already used."
    ),
    status_code=200,
    operation_id="auth_reset_password",
    responses={
        400: {"description": "Invalid, expired, or already-used reset token"},
        **_AUTH_ERRORS,
    },
)
async def reset_password_endpoint(
    body: ResetPasswordRequest,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "auth.password.reset_password",
            token=body.token,
            new_password=body.new_password,
        )
    except InvalidResetTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Password updated successfully."}
