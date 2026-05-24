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

    async def ensure_product(self, card_version_id: UUID) -> Optional[UUID]:
        """Get-or-create product_ref + mtg_card_products for a card_version. Returns product_id."""
        rows = await self.execute_query(
            sales_queries.ENSURE_PRODUCT,
            (str(card_version_id),),
        )
        if rows:
            return UUID(str(rows[0]["product_id"]))
        return None

    async def upsert_listing_template(
        self,
        app_code: str,
        product_id: UUID,
        condition_code: str,
        finish_code: str,
        language_code: str,
        marketplace_id: str,
        price_cents: Optional[int],
        quantity: int,
    ) -> Optional[UUID]:
        """Get-or-create a listing template. Returns template_id."""
        rows = await self.execute_query(
            sales_queries.UPSERT_LISTING_TEMPLATE,
            (app_code, str(product_id), condition_code, finish_code,
             language_code, marketplace_id, price_cents, quantity),
        )
        if rows:
            return UUID(str(rows[0]["template_id"]))
        return None

    async def get_listing_variant(self, item_id: str) -> Optional[dict]:
        """Return condition_id, finish_id, language_id, marketplace_id for a listed item."""
        rows = await self.execute_query(
            sales_queries.GET_LISTING_VARIANT,
            (item_id,),
        )
        return dict(rows[0]) if rows else None

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
        condition_code: str = "NM",
        finish_code: str = "NONFOIL",
        language_code: str = "en",
        marketplace_id: str = "15",
    ) -> None:
        await self.execute_command(
            sales_queries.UPSERT_ACTIVE_LISTING,
            (item_id, app_code, str(card_version_id),
             condition_code, finish_code, language_code, marketplace_id, listed_at),
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
        marketplace_id: Optional[str] = None,
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
                marketplace_id,
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

    async def upsert_price_observation(
        self,
        ts_date,
        source_product_id: int,
        price_type_id: int,
        finish_id: int,
        condition_id: int,
        language_id: int,
        data_provider_id: int,
        sold_avg_cents: int,
        sold_count: int,
    ) -> None:
        await self.execute_command(
            sales_queries.UPSERT_PRICE_OBSERVATION,
            (
                ts_date,
                source_product_id,
                price_type_id,
                finish_id,
                condition_id,
                language_id,
                data_provider_id,
                sold_avg_cents,
                sold_count,
            ),
        )

    async def get_listing_meta_batch(
        self, item_ids: list[str], app_code: str
    ) -> dict[str, dict]:
        """Return a mapping of item_id → {finish_code, condition_code} for linked listings."""
        if not item_ids:
            return {}
        rows = await self.execute_query(
            sales_queries.GET_LISTING_META_BATCH,
            (item_ids, app_code),
        )
        return {str(r["item_id"]): dict(r) for r in rows}

    async def list_local_sales(
        self, user_id: str, app_code: str, limit: int = 25, offset: int = 0
    ) -> tuple[list[dict], int]:
        rows = await self.execute_query(
            sales_queries.LIST_LOCAL_SALES,
            (user_id, app_code, limit, offset),
        )
        total = int(rows[0]["total_count"]) if rows else 0
        return [dict(r) for r in rows], total

    async def get_listing_meta(self, item_id: str, app_code: str) -> Optional[dict]:
        """Fetch card_version_id + finish/condition IDs for an active listing.

        Returns None if the listing does not exist or card_version_id is NULL.
        """
        rows = await self.execute_query(
            sales_queries.GET_LISTING_META,
            (item_id, app_code),
        )
        if not rows:
            return None
        row = dict(rows[0])
        if row["card_version_id"] is None:
            return None
        return row

    async def get_ebay_card_lookup(self) -> list[dict]:
        """Return all eBay source_products with card metadata for title-matching."""
        rows = await self.execute_query(sales_queries.GET_EBAY_CARD_LOOKUP, ())
        return [dict(r) for r in rows]

    async def list_local_sales(
        self, app_code: str, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        rows = await self.execute_query(
            sales_queries.GET_LOCAL_SALES_PAGINATED,
            (app_code, limit, offset),
        )
        count_rows = await self.execute_query(
            sales_queries.COUNT_LOCAL_SALES,
            (app_code,),
        )
        total = count_rows[0]["total"] if count_rows else 0
        return [dict(r) for r in rows], int(total)
