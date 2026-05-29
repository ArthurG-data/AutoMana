"""DB repository for sealed product pricing."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_STAGING_COLUMNS: tuple[str, ...] = (
    "sealed_uuid",
    "price_source",
    "price_type",
    "currency",
    "price_value",
    "price_date",
)

_GET_SEALED_PRODUCTS_BY_SET_SQL = """
SELECT
    sp.product_id,
    sp.name,
    sp.product_type,
    sp.mtgjson_uuid,
    s.set_code
FROM pricing.sealed_products sp
JOIN card_catalog.sets s ON s.set_id = sp.set_id
WHERE lower(s.set_code) = lower($1)
ORDER BY sp.product_type, sp.name
"""

_GET_SEALED_PRICES_BY_SET_SQL = """
SELECT
    spl.product_id,
    sp.name,
    sp.product_type,
    sp.mtgjson_uuid,
    ps.code                  AS source,
    tt.transaction_type_code AS transaction_type,
    spl.price_date,
    spl.list_low_cents,
    spl.list_avg_cents,
    spl.sold_avg_cents
FROM pricing.sealed_price_latest spl
JOIN pricing.sealed_products sp  ON sp.product_id  = spl.product_id
JOIN pricing.price_source ps     ON ps.source_id   = spl.source_id
JOIN pricing.transaction_type tt ON tt.transaction_type_id = spl.transaction_type_id
JOIN card_catalog.sets s         ON s.set_id = sp.set_id
WHERE lower(s.set_code) = lower($1)
ORDER BY sp.product_type, sp.name, ps.code
"""

_GET_SEALED_PRICE_LATEST_SQL = """
SELECT
    ps.code                  AS source,
    tt.transaction_type_code AS transaction_type,
    spl.price_date,
    spl.list_low_cents,
    spl.list_avg_cents,
    spl.sold_avg_cents
FROM pricing.sealed_price_latest spl
JOIN pricing.price_source ps     ON ps.source_id   = spl.source_id
JOIN pricing.transaction_type tt ON tt.transaction_type_id = spl.transaction_type_id
WHERE spl.product_id = $1
ORDER BY ps.code, tt.transaction_type_code
"""

_GET_SEALED_PRICE_HISTORY_SQL = """
SELECT
    po.ts_date,
    ps.code                  AS source,
    tt.transaction_type_code AS transaction_type,
    po.list_avg_cents,
    po.sold_avg_cents
FROM pricing.price_observation po
JOIN pricing.source_product sp3  ON sp3.source_product_id = po.source_product_id
JOIN pricing.price_source ps     ON ps.source_id  = sp3.source_id
JOIN pricing.sealed_products sld ON sld.product_id = sp3.product_id
JOIN pricing.transaction_type tt ON tt.transaction_type_id = po.price_type_id
WHERE sld.mtgjson_uuid = $1
  AND po.ts_date BETWEEN $2 AND $3
ORDER BY po.ts_date DESC, ps.code
"""

_UPSERT_SEALED_PRODUCT_SQL = """
WITH
existing AS (
    SELECT product_id FROM pricing.sealed_products WHERE mtgjson_uuid = $1
),
game AS (
    SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'
),
set_ref AS (
    SELECT set_id FROM card_catalog.sets WHERE lower(set_code) = lower($4)
),
new_product AS (
    INSERT INTO pricing.product_ref (game_id)
    SELECT g.game_id FROM game g
    WHERE NOT EXISTS (SELECT 1 FROM existing)
    RETURNING product_id
),
final_id AS (
    SELECT product_id FROM existing
    UNION ALL
    SELECT product_id FROM new_product
)
INSERT INTO pricing.sealed_products (product_id, set_id, name, product_type, mtgjson_uuid)
SELECT
    f.product_id,
    sr.set_id,
    $2,
    $3,
    $1
FROM final_id f
LEFT JOIN set_ref sr ON true
ON CONFLICT (mtgjson_uuid) DO UPDATE
    SET name         = EXCLUDED.name,
        product_type = EXCLUDED.product_type,
        set_id       = EXCLUDED.set_id,
        updated_at   = now()
"""

_FETCH_ALL_SEALED_UUIDS_SQL = """
SELECT mtgjson_uuid FROM pricing.sealed_products
"""


class SealedPricingRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "SealedPricingRepository"

    async def get_sealed_products_by_set(self, set_code: str) -> list[dict]:
        rows = await self.execute_query(_GET_SEALED_PRODUCTS_BY_SET_SQL, (set_code,))
        return [dict(r) for r in rows]

    async def get_sealed_prices_by_set(self, set_code: str) -> list[dict]:
        rows = await self.execute_query(_GET_SEALED_PRICES_BY_SET_SQL, (set_code,))
        return [dict(r) for r in rows]

    async def get_sealed_price_latest(self, product_id: UUID) -> list[dict]:
        rows = await self.execute_query(_GET_SEALED_PRICE_LATEST_SQL, (product_id,))
        return [dict(r) for r in rows]

    async def get_sealed_price_history(
        self,
        mtgjson_uuid: str,
        from_date: date,
        to_date: date,
    ) -> list[dict]:
        rows = await self.execute_query(
            _GET_SEALED_PRICE_HISTORY_SQL, (mtgjson_uuid, from_date, to_date)
        )
        return [dict(r) for r in rows]

    async def fetch_all_sealed_uuids(self) -> set[str]:
        rows = await self.execute_query(_FETCH_ALL_SEALED_UUIDS_SQL, ())
        return {r["mtgjson_uuid"] for r in rows}

    async def upsert_sealed_products(self, products: list[dict]) -> int:
        for product in products:
            await self.execute_command(
                _UPSERT_SEALED_PRODUCT_SQL,
                (
                    product["mtgjson_uuid"],
                    product["name"],
                    product["product_type"],
                    product["set_code"],
                ),
            )
        return len(products)

    async def copy_sealed_staging_batch(self, records: list[tuple]) -> int:
        if not records:
            return 0
        await self.execute_copy_records_to_table(
            "mtgjson_sealed_prices_staging",
            records=records,
            columns=_STAGING_COLUMNS,
            schema_name="pricing",
        )
        return len(records)

    async def promote_sealed_staging(self, batch_days: int = 30) -> None:
        await self.execute_procedure(
            "pricing.load_price_observation_from_mtgjson_sealed_staging",
            args=(batch_days,),
            timeout=14400,
        )

    async def truncate_sealed_staging(self) -> int:
        count = await self.execute_fetchval(
            "SELECT COUNT(*) FROM pricing.mtgjson_sealed_prices_staging", ()
        )
        if count:
            await self.execute_command(
                "TRUNCATE pricing.mtgjson_sealed_prices_staging", ()
            )
        return count or 0

    async def add(self, item: Any) -> None:
        raise NotImplementedError

    async def get(self, id: Any) -> Optional[Any]:
        raise NotImplementedError

    async def update(self, item: Any) -> None:
        raise NotImplementedError

    async def delete(self, id: Any) -> None:
        raise NotImplementedError

    async def list(self, *args: Any, **kwargs: Any) -> list:
        raise NotImplementedError
