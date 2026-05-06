from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx

from automana.api.schemas.auth.cookie import RefreshTokenResponse
from automana.core.exceptions.service_layer_exceptions.ebay import app_exception
from automana.core.models.ebay.auth import CreateAppRequest, TokenResponse
from automana.core.repositories.app_integration.ebay.ApiAuth_repository import EbayAuthAPIRepository
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository
from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.utils.redis_cache import get_redis_client

logger = logging.getLogger(__name__)

_ACCESS_KEY = "ebay:access_token:{user_id}:{app_code}"
_MARGIN = 60  # seconds


@ServiceRegistry.register(
    "integrations.ebay.start_oauth_flow",
    db_repositories=["auth"],
    api_repositories=["auth_oauth"],
)
async def request_auth_code(
    auth_repository: EbayAuthRepository,
    auth_oauth_repository: EbayAuthAPIRepository,
    app_code: str,
    user_id: UUID,
) -> dict:
    """Build the eBay OAuth authorization URL and log the pending request."""
    try:
        settings = await auth_repository.get_app_settings(user_id=user_id, app_code=app_code)
        if not settings:
            raise app_exception.EbayAppNotFoundException(
                f"eBay app with code {app_code} not found for user {user_id}"
            )
        scopes = await auth_repository.get_user_scopes(user_id=user_id, app_id=settings["app_id"])
        if not scopes:
            raise app_exception.EbayAppScopeNotFoundException(
                f"No scopes found for eBay app with code {app_code}"
            )
        request_id = await auth_repository.log_auth_request(
            user_id=user_id, app_id=settings["app_id"]
        )
        if not request_id:
            raise app_exception.EbayAuthRequestException("Failed to log eBay OAuth request")
        settings["scope"] = scopes
        settings["state"] = request_id
        url = await auth_oauth_repository.request_auth_code(settings)
        return {"authorization_url": url}
    except httpx.HTTPError as e:
        raise app_exception.EbayAuthRequestException(f"Failed to request eBay auth code: {e}")


def _valid_uuid(value: str) -> bool:
    """Return True only if value is a well-formed UUID string (32–36 chars)."""
    try:
        UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


@ServiceRegistry.register(
    "integrations.ebay.get_environment_callback",
    db_repositories=["auth"],
)
async def get_environment_callback(
    auth_repository: EbayAuthRepository,
    state: str,
    user_id: Optional[UUID] = None,
) -> str:
    """Resolve the eBay environment from a callback state token.

    eBay production truncates the state parameter to ~20 characters; sandbox
    drops it entirely. Both cases fall back to the latest pending request.
    """
    try:
        if state and _valid_uuid(state):
            env = await auth_repository.get_env_from_callback(user_id=user_id, state=state)
        else:
            # eBay truncated or dropped the state — fall back to latest pending.
            _, _, _, app_code = await auth_repository.get_latest_pending_request()
            env = await auth_repository.get_environment(app_code) if app_code else None
        if not env:
            raise app_exception.EbayAppNotFoundException(
                f"eBay app with state {state} not found for user {user_id}"
            )
        return env
    except httpx.HTTPError as e:
        raise app_exception.EbayAuthRequestException(f"Failed to get eBay environment: {e}")


@ServiceRegistry.register(
    "integrations.ebay.process_callback",
    db_repositories=["auth"],
    api_repositories=["auth_oauth"],
)
async def handle_callback(
    auth_repository: EbayAuthRepository,
    auth_oauth_repository: EbayAuthAPIRepository,
    code: str,
    state: UUID,
) -> dict:
    """Exchange the eBay authorization code for tokens.

    Only the refresh token is persisted (encrypted). The access token is cached
    in Redis and returned so the router can set it as a cookie.
    """
    app_id, user_id, app_code = None, None, None
    if state and _valid_uuid(state):
        app_id, user_id, app_code = await auth_repository.check_auth_request(state)
    if not app_code or not user_id:
        # eBay truncates/drops state — fall back to the latest pending request.
        _, app_id, user_id, app_code = await auth_repository.get_latest_pending_request()
    if not app_code or not user_id:
        raise ValueError(
            "Invalid authorization request: no matching pending OAuth request found"
        )

    settings = await auth_repository.get_app_settings(user_id=user_id, app_code=app_code)

    token_response: TokenResponse = await auth_oauth_repository.exchange_code_token(
        code=code,
        client_id=settings["app_id"],
        client_secret=settings["decrypted_secret"],
        redirect_uri=settings["ru_name"],
    )

    # Persist only the refresh token (encrypted).
    await auth_repository.upsert_refresh_token(
        user_id=user_id,
        app_id=app_id,
        refresh_token=token_response.refresh_token,
        expires_at=token_response.refresh_expires_on
        or datetime.now() + timedelta(days=548),
    )

    # Cache the access token in Redis — never written to disk.
    cache_key = _ACCESS_KEY.format(user_id=user_id, app_code=app_code)
    _redis = await get_redis_client()
    await _redis.setex(
        cache_key,
        max(token_response.expires_in - _MARGIN, _MARGIN),
        json.dumps({"access_token": token_response.access_token}),
    )

    logger.info(
        "ebay_oauth_complete",
        extra={"app_id": app_id, "user_id": str(user_id)},
    )
    return {
        "access_token": token_response.access_token,
        "expires_in": token_response.expires_in,
        "app_code": app_code,
        "user_id": str(user_id),
    }


@ServiceRegistry.register(
    "integrations.ebay.exchange_refresh_token",
    db_repositories=["auth"],
    api_repositories=["auth_oauth"],
)
async def exchange_refresh_token(
    auth_repository: EbayAuthRepository,
    auth_oauth_repository: EbayAuthAPIRepository,
    app_code: str,
    user_id: UUID,
) -> RefreshTokenResponse:
    """Exchange the stored refresh token for a new access token.

    The access token is cached in Redis and returned in the response body and
    as a cookie by the router. It is never written to the database.
    """
    record = await auth_repository.fetch_refresh_token(user_id=user_id, app_code=app_code)
    if not record:
        raise ValueError("No valid refresh token found")

    settings = await auth_repository.get_app_settings(user_id=user_id, app_code=app_code)
    scopes = await auth_repository.get_app_scopes(app_id=settings["app_id"])

    result = await auth_oauth_repository.exchange_refresh_token(
        refresh_token=record.refresh_token,
        app_id=settings["app_id"],
        secret=settings["decrypted_secret"],
        scope=scopes if scopes else [],
    )

    access_token = result.get("access_token")
    if not access_token:
        raise ValueError("No valid access token returned from eBay")

    expires_in = result.get("expires_in", 7200)

    # Handle refresh token rotation.
    new_refresh = result.get("refresh_token")
    if new_refresh and new_refresh != record.refresh_token:
        refresh_expires_in = result.get("refresh_token_expires_in")
        expires_at = (
            datetime.now() + timedelta(seconds=refresh_expires_in)
            if refresh_expires_in
            else record.expires_at
        )
        await auth_repository.upsert_refresh_token(
            user_id=user_id,
            app_id=settings["app_id"],
            refresh_token=new_refresh,
            expires_at=expires_at,
        )

    # Cache in Redis — access token never touches disk.
    cache_key = _ACCESS_KEY.format(user_id=user_id, app_code=app_code)
    _redis = await get_redis_client()
    await _redis.setex(
        cache_key,
        max(expires_in - _MARGIN, _MARGIN),
        json.dumps({"access_token": access_token}),
    )

    return RefreshTokenResponse(
        success=True,
        message="Refresh token exchanged successfully",
        access_token=access_token,
        expires_in=expires_in,
        expires_on=datetime.now() + timedelta(seconds=expires_in),
        token_type=result.get("token_type", "Bearer"),
        scopes=scopes,
        cookie_set=True,
        app_code=app_code,
    )


@ServiceRegistry.register(
    "integrations.ebay.register_app",
    db_repositories=["app"],
)
async def register_app(
    app_repository: EbayAppRepository,
    app_data: CreateAppRequest,
    created_by: UUID,
) -> bool:
    """Register an eBay app with the provided settings."""
    try:
        input_data = (
            app_data.ebay_app_id,
            app_data.app_name,
            app_data.redirect_uri,
            app_data.response_type,
            app_data.client_secret,
            app_data.environment.value,
            app_data.description,
            app_data.app_code,
        )
        app_code = await app_repository.add(input_data)
        if not app_code:
            raise app_exception.EbayAppRegistrationException("Failed to register eBay app")
        await app_repository.register_app_scopes(app_data.ebay_app_id, app_data.allowed_scopes)
        return app_code
    except app_exception.EbayAppRegistrationException as e:
        raise app_exception.EbayAppRegistrationException(f"Failed to register eBay app: {e}")


@ServiceRegistry.register(
    "integrations.ebay.get_environment",
    db_repositories=["auth"],
)
async def get_environment(
    auth_repository: EbayAuthRepository,
    app_code: str,
    user_id: Optional[UUID] = None,
) -> str:
    """Return the eBay environment (SANDBOX / PRODUCTION) for an app."""
    try:
        env = await auth_repository.get_environment(user_id=user_id, app_code=app_code)
        if not env:
            raise app_exception.EbayEnvironmentException("No valid environment found")
        return env
    except app_exception.EbayEnvironmentException as e:
        raise app_exception.EbayEnvironmentException(f"Failed to get environment: {e}")


@ServiceRegistry.register(
    "integrations.ebay.update_app_redirect_uri",
    db_repositories=["app"],
)
async def update_app_redirect_uri(
    app_repository: EbayAppRepository,
    app_code: str,
    redirect_uri: str,
) -> bool:
    """Update the redirect_uri stored for an eBay app."""
    updated = await app_repository.update_redirect_uri(app_code, redirect_uri)
    if not updated:
        raise app_exception.EbayAppNotFoundException(
            f"eBay app with code {app_code!r} not found"
        )
    return updated
