"""eBay access-token resolution — Redis-first, refresh-token fallback.

Design
------
Access tokens are volatile (~2 h). They are never written to disk.
On a Redis cache miss the encrypted refresh token is fetched from Postgres,
exchanged at eBay, the fresh access token is cached in Redis for its remaining
lifetime, and the string is returned to the caller.

Refresh token rotation: eBay occasionally issues a new refresh token alongside
the access token. When that happens the encrypted row is upserted immediately
so the old token is never presented again.

FOR UPDATE on the Postgres fetch serialises concurrent refresh attempts on the
same (user_id, app_id) row. Full race-free serialisation requires the caller
to hold an explicit transaction; that upgrade is a follow-up task.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.utils.redis_cache import get_redis_client

logger = logging.getLogger(__name__)

_KEY = "ebay:access_token:{user_id}:{app_code}"
_MARGIN = 60  # seconds — expire cache slightly before eBay does


async def resolve_token(
    auth_repository: EbayAuthRepository,
    user_id: UUID,
    app_code: str,
) -> str:
    """Return a valid eBay access token, refreshing transparently on cache miss.

    Raises ValueError when no refresh token is available — user has not
    completed OAuth or consent was revoked. Callers treat this as 4xx.
    """
    if not app_code:
        raise ValueError("app_code is required to resolve an eBay access token")

    cache_key = _KEY.format(user_id=user_id, app_code=app_code)

    _redis = await get_redis_client()
    cached = await _redis.get(cache_key)
    if cached:
        logger.info("ebay_token_cache_hit", extra={"app_code": app_code, "user_id": str(user_id)})
        return json.loads(cached)["access_token"]

    record = await auth_repository.fetch_refresh_token(user_id=user_id, app_code=app_code)
    if not record:
        logger.error(
            "ebay_token_not_found",
            extra={"action": "resolve_token", "user_id": str(user_id), "app_code": app_code},
        )
        raise ValueError(f"No valid eBay refresh token for app_code={app_code!r}")

    settings = await auth_repository.get_app_settings(user_id=user_id, app_code=app_code)
    scopes = await auth_repository.get_app_scopes(app_id=settings["app_id"])

    # Import deferred to avoid circular dependency at module load time.
    from automana.core.repositories.app_integration.ebay.ApiAuth_repository import (
        EbayAuthAPIRepository,
    )

    api_repo = EbayAuthAPIRepository(environment=settings["environment"].lower())
    result = await api_repo.exchange_refresh_token(
        refresh_token=record.refresh_token,
        app_id=settings["app_id"],
        secret=settings["decrypted_secret"],
        scope=scopes,
    )

    access_token = result.get("access_token")
    if not access_token:
        raise ValueError(f"eBay token exchange returned no access_token for app_code={app_code!r}")

    # Handle refresh token rotation (eBay may issue a new refresh token).
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
        logger.info(
            "ebay_refresh_token_rotated",
            extra={"app_code": app_code, "user_id": str(user_id)},
        )

    expires_in = result.get("expires_in", 7200)
    _redis = await get_redis_client()
    await _redis.setex(
        cache_key,
        max(expires_in - _MARGIN, _MARGIN),
        json.dumps({"access_token": access_token}),
    )
    logger.info("ebay_token_cache_populated", extra={"app_code": app_code, "user_id": str(user_id)})

    return access_token
