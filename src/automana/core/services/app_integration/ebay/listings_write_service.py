"""eBay listings — write side (CQS: Commands).

Design patterns
───────────────
- **CQS (Command–Query Separation)**: this module owns commands only
  (``create_listing``, ``update_listing``, ``end_listing``). Reads live in
  ``listings_read_service``. Two sides, two files — the old fat dispatcher
  violated this boundary and paid for it in cyclomatic complexity.
- **Command**: each registered function is one business-intent command,
  typed end-to-end. No ``action: str`` string keys, no ``payload: dict[str,
  Any]`` bags at the public boundary — those are exactly the god-object /
  stringly-typed smells our Gordon-Ramsay-sense was built to detect.
- **Guard Clause** via ``_auth_context.resolve_token`` at the top of each
  function. Fail fast, fail loud, fail before spending the API call budget.
- **Idempotency Key** (Enterprise pattern): ``create_listing`` accepts a
  client-supplied ``idempotency_key`` and consults a Redis SETNX store to
  short-circuit duplicate creates. Update and end are naturally idempotent
  when keyed by ``item_id`` and therefore don't need this ceremony.

Project rules honoured
──────────────────────
- ``logger = logging.getLogger(__name__)``; no ``logging.basicConfig``.
- ``extra={}`` uses non-reserved field names only
  (``user_id``, ``app_code``, ``action``, ``idempotency_key``, ``item_id``).
- Exceptions are plain ``ValueError`` / ``RuntimeError`` pending the
  dedicated ``EbaySellingError`` hierarchy PR — see the TODOs.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from automana.core.models.ebay import listings as listings_model
from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import (
    EbaySellingRepository,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token
from automana.core.services.app_integration.ebay._idempotency import (
    get_idempotency_store,
)

logger = logging.getLogger(__name__)

# eBay UK site id. Magic numbers are rude; named constants are manners.
DEFAULT_MARKETPLACE_ID: str = "15"


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.create",
    db_repositories=["auth"],
    api_repositories=["selling"],
)
async def create_listing(
    auth_repository: EbayAuthRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    item: listings_model.ItemModel,
    idempotency_key: str,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Create a new eBay listing (Command pattern + Idempotency Key).

    The ``idempotency_key`` is mandatory. The router enforces its presence
    via the ``Idempotency-Key`` HTTP header; if that contract is broken,
    this function fails closed.
    """
    # TODO(exceptions): migrate to EbaySellingError hierarchy once
    # core/exceptions/service_layer_exceptions/ebay/ lands.
    if not idempotency_key:
        raise ValueError("idempotency_key is required for create_listing")

    logger.info(
        "ebay_create_listing_requested",
        extra={
            "action": "create_listing",
            "user_id": str(user_id),
            "app_code": app_code,
            "idempotency_key": idempotency_key,
        },
    )

    store = get_idempotency_store()
    cached = store.get(idempotency_key)
    if cached is not None:
        logger.info(
            "ebay_create_listing_idempotent_hit",
            extra={
                "action": "create_listing",
                "idempotency_key": idempotency_key,
                "user_id": str(user_id),
            },
        )
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            # Legacy / malformed entry — treat as miss, overwrite below.
            logger.warning(
                "ebay_create_listing_cache_decode_failed",
                extra={
                    "action": "create_listing",
                    "idempotency_key": idempotency_key,
                },
            )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)

    # The repository still wants a dict payload; that is a repo-layer
    # limitation we do not fix in this PR. The service layer above it, the
    # bit users actually call, is now typed. One boundary at a time.
    payload: Dict[str, Any] = {
        "item": item,
        "token": token,
        "marketplace_id": marketplace_id,
    }
    result = await selling_repository.create_listing(payload)

    # Best-effort cache write. Failure is logged inside the store and
    # intentionally does NOT fail the request.
    try:
        store.set_if_absent(idempotency_key, json.dumps(result, default=str))
    except (TypeError, ValueError) as exc:
        logger.warning(
            "ebay_create_listing_cache_encode_failed",
            extra={
                "action": "create_listing",
                "idempotency_key": idempotency_key,
                "error": str(exc),
            },
        )

    return result


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.update",
    db_repositories=["auth"],
    api_repositories=["selling"],
)
async def update_listing(
    auth_repository: EbayAuthRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    item: listings_model.ItemModel,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Update an existing eBay listing (naturally idempotent by `item.ItemID`)."""
    # TODO(exceptions): migrate to EbaySellingError hierarchy once
    # core/exceptions/service_layer_exceptions/ebay/ lands.
    logger.info(
        "ebay_update_listing_requested",
        extra={
            "action": "update_listing",
            "user_id": str(user_id),
            "app_code": app_code,
            "item_id": getattr(item, "ItemID", None),
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    payload: Dict[str, Any] = {
        "item": item,
        "token": token,
        "marketplace_id": marketplace_id,
    }
    return await selling_repository.update_listing(payload)


@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.end",
    db_repositories=["auth"],
    api_repositories=["selling"],
)
async def end_listing(
    auth_repository: EbayAuthRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    item_id: str,
    ending_reason: str = "NotAvailable",
    verify: bool = False,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    **kwargs: Any,
) -> Dict[str, Any]:
    """End (not "delete") an eBay listing — idempotent when keyed by `item_id`.

    Named ``end_listing`` rather than ``delete_listing`` because eBay's
    Trading API calls this ``EndItem``. "Delete" would lie about what the
    platform is doing. Precision in the ubiquitous language is not pedantry;
    it's how you stop on-call pages at 3 AM.
    """
    # TODO(exceptions): migrate to EbaySellingError hierarchy once
    # core/exceptions/service_layer_exceptions/ebay/ lands.
    if not item_id:
        raise ValueError("item_id is required for end_listing")

    logger.info(
        "ebay_end_listing_requested",
        extra={
            "action": "end_listing",
            "user_id": str(user_id),
            "app_code": app_code,
            "item_id": item_id,
            "ending_reason": ending_reason,
            "verify": verify,
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    payload: Dict[str, Any] = {
        "token": token,
        "item_id": item_id,
        "ending_reason": ending_reason,
        "verify": verify,
        "marketplace_id": marketplace_id,
    }
    return await selling_repository.delete_listing(payload)
