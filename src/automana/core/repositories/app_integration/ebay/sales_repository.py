"""DB repository for eBay sold-price persistence (own-sales channel)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)
from automana.core.repositories.app_integration.ebay import sales_queries

logger = logging.getLogger(__name__)


class EbaySalesRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "EbaySalesRepository"

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

    async def ensure_source_product(
        self, card_version_id: UUID, source_id: int
    ) -> Optional[int]:
        """Get-or-create a source_product row for a card_version. Returns source_product_id."""
        rows = await self.execute_query(
            sales_queries.ENSURE_SOURCE_PRODUCT,
            (str(card_version_id), source_id),
        )
        if rows:
            return rows[0]["source_product_id"]
        return None

    async def upsert_active_listing(
        self,
        item_id: str,
        app_code: str,
        card_version_id: UUID,
        listed_at: datetime,
    ) -> None:
        await self.execute_command(
            sales_queries.UPSERT_ACTIVE_LISTING,
            (item_id, app_code, str(card_version_id), listed_at),
        )

    async def get_card_version_by_item(self, item_id: str) -> Optional[UUID]:
        rows = await self.execute_query(
            sales_queries.GET_CARD_VERSION_BY_ITEM,
            (item_id,),
        )
        if rows:
            return UUID(str(rows[0]["card_version_id"]))
        return None

    async def get_listed_card_versions(self, app_code: str) -> list[UUID]:
        rows = await self.execute_query(
            sales_queries.GET_LISTED_CARD_VERSIONS,
            (app_code,),
        )
        return [UUID(str(r["card_version_id"])) for r in rows]

    async def upsert_order_source_product(
        self,
        order_id: str,
        app_code: str,
        item_id: str,
        title: str,
        source_product_id: Optional[int],
        quantity: int,
        sold_price_cents: int,
        currency: str,
        finish_id: int,
        condition_id: Optional[int],
        language_id: int,
        sold_at: datetime,
        buyer_username: Optional[str],
    ) -> None:
        await self.execute_command(
            sales_queries.UPSERT_ORDER_SOURCE_PRODUCT,
            (
                order_id,
                app_code,
                item_id,
                title,
                source_product_id,
                quantity,
                sold_price_cents,
                currency,
                finish_id,
                condition_id,
                language_id,
                sold_at,
                buyer_username,
            ),
        )

    async def get_unpromoted(self) -> list[dict]:
        rows = await self.execute_query(
            sales_queries.GET_UNPROMOTED_OWN_SALES, ()
        )
        return [dict(r) for r in rows]

    async def mark_promoted(self, ebay_osp_ids: list[int]) -> None:
        if not ebay_osp_ids:
            return
        await self.execute_command(
            sales_queries.MARK_OWN_SALES_PROMOTED,
            (ebay_osp_ids,),
        )
