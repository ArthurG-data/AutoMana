from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.actions.stage",
    db_repositories=["listing_actions"],
)
async def stage_action(
    listing_actions_repository,
    user_id: UUID,
    app_code: str,
    item_id: str,
    action_type: str,
    strategy_kind: str,
    suggested_price: Optional[float],
) -> dict:
    existing = await listing_actions_repository.get_pending_for_item(item_id)
    if existing is not None:
        logger.info("Action staged", extra={"item_id": item_id, "action_type": action_type, "created": False})
        return {"action_id": existing["id"], "created": False}

    new_id = await listing_actions_repository.insert_action(
        item_id, user_id, app_code, action_type, strategy_kind, suggested_price
    )
    logger.info("Action staged", extra={"item_id": item_id, "action_type": action_type, "created": True})
    return {"action_id": new_id, "created": True}


@ServiceRegistry.register(
    path="integrations.ebay.actions.get_pending",
    db_repositories=["listing_actions"],
)
async def get_pending_action(
    listing_actions_repository,
    item_id: str,
) -> Optional[dict]:
    return await listing_actions_repository.get_pending_for_item(item_id)
