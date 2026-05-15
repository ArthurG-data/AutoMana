from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_INSERT = """
INSERT INTO app_integration.listing_pending_actions
    (item_id, user_id, app_code, action_type, strategy_kind, suggested_price)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING id;
"""

_GET_PENDING = """
SELECT id, item_id, user_id, app_code, action_type, strategy_kind, suggested_price, status
FROM app_integration.listing_pending_actions
WHERE status = 'pending'
ORDER BY created_at
LIMIT $1;
"""

_MARK_PROCESSING = """
UPDATE app_integration.listing_pending_actions
SET status = 'processing'
WHERE id = $1;
"""

_MARK_DONE = """
UPDATE app_integration.listing_pending_actions
SET status = 'done', executed_at = now()
WHERE id = $1;
"""

_MARK_FAILED = """
UPDATE app_integration.listing_pending_actions
SET status = 'failed', error = $1
WHERE id = $2;
"""

_GET_PENDING_FOR_ITEM = """
SELECT id, item_id, user_id, app_code, action_type, strategy_kind, suggested_price, status
FROM app_integration.listing_pending_actions
WHERE item_id = $1 AND status IN ('pending', 'processing')
ORDER BY created_at DESC
LIMIT 1;
"""


class EbayListingActionsRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "EbayListingActionsRepository"

    async def add(self, item=None) -> None:
        pass

    async def get(self, id=None):
        return None

    async def update(self, item=None) -> None:
        pass

    async def delete(self, id=None) -> None:
        pass

    async def list(self, items=None) -> list:
        return []

    async def insert_action(
        self,
        item_id: str,
        user_id: UUID,
        app_code: str,
        action_type: str,
        strategy_kind: str,
        suggested_price: Optional[float],
    ) -> str:
        rows = await self.execute_query(
            _INSERT,
            (item_id, user_id, app_code, action_type, strategy_kind, suggested_price),
        )
        return str(rows[0]['id'])

    async def get_pending(self, limit: int = 50) -> list[dict]:
        rows = await self.execute_query(_GET_PENDING, (limit,))
        return list(rows)

    async def mark_processing(self, action_id: UUID) -> None:
        await self.execute_command(_MARK_PROCESSING, (action_id,))

    async def mark_done(self, action_id: UUID) -> None:
        await self.execute_command(_MARK_DONE, (action_id,))

    async def mark_failed(self, action_id: UUID, error: str) -> None:
        await self.execute_command(_MARK_FAILED, (error, action_id))

    async def get_pending_for_item(self, item_id: str) -> Optional[dict]:
        rows = await self.execute_query(_GET_PENDING_FOR_ITEM, (item_id,))
        return rows[0] if rows else None
