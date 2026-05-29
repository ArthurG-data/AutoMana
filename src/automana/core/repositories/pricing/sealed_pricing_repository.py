"""DB repository for sealed product pricing."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

# ── Staging pipeline ──────────────────────────────────────────────────────────

_STAGING_COLUMNS: tuple[str, ...] = (
    "sealed_uuid",
    "price_source",
    "price_type",
    "currency",
    "price_value",
    "price_date",
)

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

# ── Read queries ──────────────────────────────────────────────────────────────

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
    msp.product_id,
    sp.sealed_product_id,
    sp.name,
    str.type_code,
    ssr.subtype_code,
    lr.language_code,
    ps.code                  AS source,
    tt.transaction_type_code AS transaction_type,
    spl.price_date,
    spl.list_low_cents,
    spl.list_avg_cents,
    spl.sold_avg_cents,
    uuid_id.value            AS mtgjson_uuid,
    tcg_id.value             AS tcgplayer_product_id
FROM pricing.mtg_sealed_products msp
JOIN card_catalog.sealed_product sp  ON sp.sealed_product_id = msp.sealed_product_id
JOIN card_catalog.sets s             ON s.set_id  = sp.set_id
JOIN card_catalog.sealed_type_ref str ON str.sealed_type_id = sp.sealed_type_id
LEFT JOIN card_catalog.sealed_subtype_ref ssr ON ssr.sealed_subtype_id = sp.sealed_subtype_id
JOIN card_catalog.language_ref lr    ON lr.language_id = sp.language_id
JOIN pricing.sealed_price_latest spl ON spl.product_id = msp.product_id
JOIN pricing.price_source ps         ON ps.source_id   = spl.source_id
JOIN pricing.transaction_type tt     ON tt.transaction_type_id = spl.transaction_type_id
LEFT JOIN card_catalog.sealed_identifier_ref uuid_ref
    ON uuid_ref.identifier_name = 'mtgjson_uuid'
LEFT JOIN card_catalog.sealed_external_identifier uuid_id
    ON uuid_id.sealed_product_id = sp.sealed_product_id
   AND uuid_id.sealed_identifier_ref_id = uuid_ref.sealed_identifier_ref_id
LEFT JOIN card_catalog.sealed_identifier_ref tcg_ref
    ON tcg_ref.identifier_name = 'tcgplayer_product_id'
LEFT JOIN card_catalog.sealed_external_identifier tcg_id
    ON tcg_id.sealed_product_id = sp.sealed_product_id
   AND tcg_id.sealed_identifier_ref_id = tcg_ref.sealed_identifier_ref_id
WHERE lower(s.set_code) = lower($1)
ORDER BY str.type_code, ssr.subtype_code NULLS LAST, sp.name, ps.code
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
JOIN pricing.source_product sprod ON sprod.source_product_id = po.source_product_id
JOIN pricing.price_source ps      ON ps.source_id  = sprod.source_id
JOIN pricing.mtg_sealed_products msp ON msp.product_id = sprod.product_id
JOIN card_catalog.sealed_product sp  ON sp.sealed_product_id = msp.sealed_product_id
JOIN pricing.transaction_type tt  ON tt.transaction_type_id = po.price_type_id
JOIN card_catalog.sealed_external_identifier sei
    ON sei.sealed_product_id = sp.sealed_product_id
JOIN card_catalog.sealed_identifier_ref sir
    ON sir.sealed_identifier_ref_id = sei.sealed_identifier_ref_id
   AND sir.identifier_name = 'mtgjson_uuid'
WHERE sei.value = $1
  AND po.ts_date BETWEEN $2 AND $3
ORDER BY po.ts_date DESC, ps.code
"""

# ── Ref-map loaders (called once per upsert batch) ────────────────────────────

_FETCH_TYPE_REF_SQL = """
SELECT sealed_type_id, type_code FROM card_catalog.sealed_type_ref
"""
_FETCH_SUBTYPE_REF_SQL = """
SELECT sealed_subtype_id, subtype_code FROM card_catalog.sealed_subtype_ref
"""
_FETCH_IDENTIFIER_REF_SQL = """
SELECT sealed_identifier_ref_id, identifier_name FROM card_catalog.sealed_identifier_ref
"""

# ── Upsert helpers ────────────────────────────────────────────────────────────

_FIND_SEALED_PRODUCT_BY_UUID_SQL = """
SELECT sei.sealed_product_id
FROM card_catalog.sealed_external_identifier sei
JOIN card_catalog.sealed_identifier_ref sir
    ON sir.sealed_identifier_ref_id = sei.sealed_identifier_ref_id
WHERE sir.identifier_name = 'mtgjson_uuid'
  AND sei.value = $1
"""

_FIND_SEALED_PRODUCT_BY_TCGPLAYER_ID_SQL = """
SELECT sei.sealed_product_id
FROM card_catalog.sealed_external_identifier sei
JOIN card_catalog.sealed_identifier_ref sir
    ON sir.sealed_identifier_ref_id = sei.sealed_identifier_ref_id
WHERE sir.identifier_name = 'tcgplayer_product_id'
  AND sei.value = $1
"""

_INSERT_SEALED_PRODUCT_SQL = """
INSERT INTO card_catalog.sealed_product
    (set_id, game_id, sealed_type_id, sealed_subtype_id, language_id, name, release_date)
SELECT
    (SELECT set_id FROM card_catalog.sets WHERE lower(set_code) = lower($1)),
    (SELECT game_id FROM card_catalog.card_games_ref WHERE code = $2),
    $3, $4,
    (SELECT language_id FROM card_catalog.language_ref WHERE language_code = $5),
    $6, $7
RETURNING sealed_product_id
"""

_UPDATE_SEALED_PRODUCT_SQL = """
UPDATE card_catalog.sealed_product
SET name               = $2,
    set_id             = (SELECT set_id FROM card_catalog.sets WHERE lower(set_code) = lower($3)),
    sealed_type_id     = $4,
    sealed_subtype_id  = $5,
    release_date       = $6,
    updated_at         = now()
WHERE sealed_product_id = $1
"""

_UPSERT_EXTERNAL_ID_SQL = """
INSERT INTO card_catalog.sealed_external_identifier
    (sealed_identifier_ref_id, sealed_product_id, value)
VALUES ($1, $2, $3)
ON CONFLICT (sealed_product_id, sealed_identifier_ref_id)
    DO UPDATE SET value = EXCLUDED.value
"""

_UPSERT_TYPE_REF_SQL = """
INSERT INTO card_catalog.sealed_type_ref (type_code)
VALUES ($1)
ON CONFLICT (type_code) DO UPDATE SET type_code = EXCLUDED.type_code
RETURNING sealed_type_id
"""

_UPSERT_SUBTYPE_REF_SQL = """
INSERT INTO card_catalog.sealed_subtype_ref (subtype_code)
VALUES ($1)
ON CONFLICT (subtype_code) DO UPDATE SET subtype_code = EXCLUDED.subtype_code
RETURNING sealed_subtype_id
"""

_INSERT_PRODUCT_REF_SQL = """
INSERT INTO pricing.product_ref (game_id)
SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'
RETURNING product_id
"""

_FIND_PRODUCT_ID_BY_SEALED_PRODUCT_SQL = """
SELECT product_id FROM pricing.mtg_sealed_products WHERE sealed_product_id = $1
"""

_INSERT_MTG_SEALED_PRODUCT_SQL = """
INSERT INTO pricing.mtg_sealed_products (product_id, sealed_product_id)
VALUES ($1, $2)
ON CONFLICT (product_id) DO NOTHING
"""


class SealedPricingRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "SealedPricingRepository"

    # ── Queries ───────────────────────────────────────────────────────────────

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

    async def fetch_sealed_product_id_by_mtgjson_uuid(self, mtgjson_uuid: str) -> UUID | None:
        return await self.execute_fetchval(
            _FIND_SEALED_PRODUCT_BY_UUID_SQL, (mtgjson_uuid,)
        )

    async def fetch_sealed_product_id_by_tcgplayer_id(
        self, tcgplayer_product_id: str
    ) -> UUID | None:
        return await self.execute_fetchval(
            _FIND_SEALED_PRODUCT_BY_TCGPLAYER_ID_SQL, (tcgplayer_product_id,)
        )

    async def fetch_all_sealed_uuids(self) -> set[str]:
        rows = await self.execute_query(_FETCH_ALL_SEALED_UUIDS_SQL, ())
        return {r["mtgjson_uuid"] for r in rows}

    # ── Commands ──────────────────────────────────────────────────────────────

    async def upsert_sealed_catalog(self, products: list[dict]) -> int:
        """Upsert sealed product catalog rows.

        Each dict must contain: mtgjson_uuid, name, set_code, type_code, game_code,
        language_code. Optional: subtype_code (None = no subtype), release_date,
        tcgplayer_product_id, cardkingdom_id, mcm_id, scg_id, abu_id.

        Idempotent — re-running with the same mtgjson_uuid updates name, set, and
        type in place; new external identifiers are inserted without disturbing
        existing ones.
        """
        type_map: dict[str, int] = {
            r["type_code"]: r["sealed_type_id"]
            for r in await self.execute_query(_FETCH_TYPE_REF_SQL, ())
        }
        subtype_map: dict[str, int] = {
            r["subtype_code"]: r["sealed_subtype_id"]
            for r in await self.execute_query(_FETCH_SUBTYPE_REF_SQL, ())
        }
        id_ref_map: dict[str, int] = {
            r["identifier_name"]: r["sealed_identifier_ref_id"]
            for r in await self.execute_query(_FETCH_IDENTIFIER_REF_SQL, ())
        }

        for product in products:
            type_code = product["type_code"]
            if type_code not in type_map:
                type_id = await self.execute_fetchval(_UPSERT_TYPE_REF_SQL, (type_code,))
                type_map[type_code] = type_id
            type_id = type_map[type_code]

            raw_subtype = product.get("subtype_code") or ""
            subtype_id: int | None = None
            if raw_subtype:
                if raw_subtype not in subtype_map:
                    sub_id = await self.execute_fetchval(
                        _UPSERT_SUBTYPE_REF_SQL, (raw_subtype,)
                    )
                    subtype_map[raw_subtype] = sub_id
                subtype_id = subtype_map[raw_subtype]

            mtgjson_uuid = product["mtgjson_uuid"]
            sealed_product_id = await self.execute_fetchval(
                _FIND_SEALED_PRODUCT_BY_UUID_SQL, (mtgjson_uuid,)
            )

            if sealed_product_id is None:
                sealed_product_id = await self.execute_fetchval(
                    _INSERT_SEALED_PRODUCT_SQL,
                    (
                        product["set_code"],
                        product.get("game_code", "mtg"),
                        type_id,
                        subtype_id,
                        product.get("language_code", "en"),
                        product["name"],
                        product.get("release_date"),
                    ),
                )
            else:
                await self.execute_command(
                    _UPDATE_SEALED_PRODUCT_SQL,
                    (
                        sealed_product_id,
                        product["name"],
                        product["set_code"],
                        type_id,
                        subtype_id,
                        product.get("release_date"),
                    ),
                )

            # Upsert every external identifier present in the product dict
            identifier_keys = {
                "mtgjson_uuid", "tcgplayer_product_id",
                "cardkingdom_id", "mcm_id", "scg_id", "abu_id",
            }
            for id_name in identifier_keys:
                value = product.get(id_name)
                if value and id_name in id_ref_map:
                    await self.execute_command(
                        _UPSERT_EXTERNAL_ID_SQL,
                        (id_ref_map[id_name], sealed_product_id, str(value)),
                    )

            # Ensure pricing.mtg_sealed_products row exists
            product_id = await self.execute_fetchval(
                _FIND_PRODUCT_ID_BY_SEALED_PRODUCT_SQL, (sealed_product_id,)
            )
            if product_id is None:
                product_id = await self.execute_fetchval(_INSERT_PRODUCT_REF_SQL, ())
                await self.execute_command(
                    _INSERT_MTG_SEALED_PRODUCT_SQL, (product_id, sealed_product_id)
                )

        return len(products)

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
