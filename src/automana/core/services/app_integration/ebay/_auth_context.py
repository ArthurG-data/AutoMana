"""Private helpers for resolving an eBay OAuth access token at the service layer.

Design patterns
───────────────
- **Guard Clause**: one-line token validation raises `ValueError` before any
  expensive work. Every registered selling service calls `resolve_token(...)`
  at the top of its body, short-circuiting on missing credentials.
- **Parameter Object (light)**: callers pass the two identifying fields
  (`user_id`, `app_code`) directly rather than stuffing a dict payload.
  Because guess what, Gordon: a `payload: dict[str, Any]` arriving at the
  service layer is the god-object of our times. We do not feed god objects.

This module is intentionally **not** registered as a service. Token acquisition
is a one-liner plumbing concern, not a bounded behaviour worthy of a
`ServiceRegistry` entry. If you find yourself tempted to register it, stop and
inspect the urge — you probably just want to inject `auth_repository`.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)

logger = logging.getLogger(__name__)


async def resolve_token(
    auth_repository: EbayAuthRepository,
    user_id: UUID,
    app_code: str,
) -> str:
    """Return a valid access token or raise — no ambiguity, no `None` leaking.

    Applies the Guard Clause pattern. Raises `ValueError` (deliberately plain —
    see the TODO in every call site) when the auth repository has no live
    access token for the `(user_id, app_code)` tuple. Callers should treat
    this as a 4xx-worthy condition.
    """
    # TODO(exceptions): migrate to EbaySellingError hierarchy once
    # core/exceptions/service_layer_exceptions/ebay/ lands.
    if not app_code:
        # Yes, this belongs to the caller's validation, but eBay's OAuth will
        # happily 500 on a silent empty string — cheaper to reject here.
        raise ValueError("app_code is required to resolve an eBay access token")

    token: Optional[str] = await auth_repository.get_valid_access_token(
        user_id=user_id, app_code=app_code
    )
    if not token:
        logger.error(
            "ebay_token_not_found",
            extra={
                "action": "resolve_token",
                "user_id": str(user_id) if user_id else None,
                "app_code": app_code,
            },
        )
        raise ValueError(
            f"No valid eBay access token for app_code={app_code!r}"
        )
    return token
