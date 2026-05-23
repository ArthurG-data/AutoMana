from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.framework.registry import ServiceRegistry

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
        logger.info("Action staged", extra={"item_id": item_id, "action_type": action_type, "is_new": False})
        return {"action_id": existing["id"], "created": False}

    new_id = await listing_actions_repository.insert_action(
        item_id, user_id, app_code, action_type, strategy_kind, suggested_price
    )
    logger.info("Action staged", extra={"item_id": item_id, "action_type": action_type, "is_new": True})
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


@ServiceRegistry.register(
    path="integrations.ebay.actions.drain",
    db_repositories=["listing_actions"],
    runs_in_transaction=False,  # each action commits independently
)
async def drain_pending_actions(
    listing_actions_repository,
    limit: int = 50,
) -> dict:
    rows = await listing_actions_repository.get_pending(limit=limit)
    processed = 0
    failed = 0
    for row in rows:
        action_id = row["id"]
        try:
            await listing_actions_repository.mark_processing(action_id)
            # NOTE: actual eBay API call would go here in a future task
            # For now, log the intended action and mark done
            logger.info(
                "action_processed",
                extra={
                    "action_id": str(action_id),
                    "item_id": row["item_id"],
                    "action_type": row["action_type"],
                    "suggested_price": row.get("suggested_price"),
                },
            )
            await listing_actions_repository.mark_done(action_id)
            processed += 1
        except Exception as exc:
            await listing_actions_repository.mark_failed(action_id, str(exc))
            logger.warning(
                "action_failed",
                extra={"action_id": str(action_id), "error": str(exc)},
            )
            failed += 1
    return {"processed": processed, "failed": failed}
