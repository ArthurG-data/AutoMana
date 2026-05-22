"""DB repository for eBay sold-price persistence (external scrape channel)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)
from automana.core.repositories.app_integration.ebay import ebay_scrape_queries

logger = logging.getLogger(__name__)


class EbayScrapeSoldRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "EbayScrapeSoldRepository"

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

    async def insert_scraped_sold(
        self,
        item_id: str,
        title: str,
        source_product_id: Optional[int],
        price_cents: int,
        currency: str,
        marketplace_id: str,
        condition_id: int,
        finish_id: int,
        language_id: int,
        sold_at: datetime,
    ) -> None:
        await self.execute_command(
            ebay_scrape_queries.INSERT_SCRAPED_SOLD,
            (
                item_id,
                title,
                source_product_id,
                price_cents,
                currency,
                marketplace_id,
                condition_id,
                finish_id,
                language_id,
                sold_at,
            ),
        )

    async def get_unpromoted(self) -> list[dict]:
        rows = await self.execute_query(
            ebay_scrape_queries.GET_UNPROMOTED_SCRAPED, ()
        )
        return [dict(r) for r in rows]

    async def mark_promoted(self, scrape_ids: list[int]) -> None:
        if not scrape_ids:
            return
        await self.execute_command(
            ebay_scrape_queries.MARK_SCRAPED_PROMOTED,
            (scrape_ids,),
        )

    async def get_scrape_targets(self) -> list[UUID]:
        rows = await self.execute_query(ebay_scrape_queries.GET_SCRAPE_TARGETS, ())
        return [UUID(str(r["card_version_id"])) for r in rows]

    async def refresh_scrape_targets(self, min_cents: int) -> None:
        await self.execute_command(
            ebay_scrape_queries.REFRESH_SCRAPE_TARGETS, (min_cents,)
        )

    async def update_target_last_scraped(self, card_version_id: UUID) -> None:
        await self.execute_command(
            ebay_scrape_queries.UPDATE_TARGET_LAST_SCRAPED, (str(card_version_id),)
        )
