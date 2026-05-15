from datetime import date
from typing import Optional
import logging

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)


_RESOLVE_SCRYFALL_IDS_SQL = """
SELECT
    ei.value AS scryfall_id,
    ei.card_version_id,
    mcp.product_id
FROM card_catalog.card_external_identifier ei
JOIN card_catalog.card_identifier_ref ir USING (card_identifier_ref_id)
LEFT JOIN pricing.mtg_card_products mcp USING (card_version_id)
WHERE ir.identifier_name = 'scryfall_id'
AND ei.value = ANY($1::text[])
"""

_INSERT_PRODUCTS_BATCH_SQL = """
WITH unlinked AS (
    SELECT cv_id
    FROM unnest($1::uuid[]) AS cv_id
    WHERE NOT EXISTS (
        SELECT 1 FROM pricing.mtg_card_products mcp WHERE mcp.card_version_id = cv_id
    )
),
ins_product AS (
    INSERT INTO pricing.product_ref (game_id)
    SELECT (SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg')
    FROM unlinked
    RETURNING product_id
),
numbered_products AS (
    SELECT product_id, row_number() OVER () AS rn FROM ins_product
),
numbered_cards AS (
    SELECT cv_id, row_number() OVER () AS rn FROM unlinked
),
zipped AS (
    SELECT np.product_id, nc.cv_id AS card_version_id
    FROM numbered_products np JOIN numbered_cards nc USING (rn)
)
INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
SELECT product_id, card_version_id FROM zipped
ON CONFLICT (card_version_id) DO NOTHING
RETURNING product_id, card_version_id
"""

_GET_PRODUCT_IDS_FOR_CARDS_SQL = """
SELECT mcp.card_version_id, mcp.product_id
FROM pricing.mtg_card_products mcp
WHERE mcp.card_version_id = ANY($1::uuid[])
"""

_ENSURE_SOURCE_PRODUCT_SQL = """
INSERT INTO pricing.source_product (product_id, source_id)
SELECT
    v.product_id::uuid,
    ps.source_id
FROM unnest($1::uuid[], $2::text[]) AS v(product_id, source_code)
JOIN pricing.price_source ps ON ps.code = v.source_code
ON CONFLICT (product_id, source_id) DO NOTHING
"""

_FETCH_SOURCE_PRODUCT_IDS_SQL = """
SELECT sp.source_product_id, sp.product_id, ps.code AS source_code
FROM pricing.source_product sp
JOIN pricing.price_source ps USING (source_id)
WHERE sp.product_id = ANY($1::uuid[])
AND ps.code = ANY($2::text[])
"""

_UPSERT_PRICE_OBSERVATION_SQL = """
INSERT INTO pricing.price_observation (
    ts_date, source_product_id, price_type_id, finish_id,
    condition_id, language_id, data_provider_id, list_avg_cents, scraped_at
)
SELECT
    $1::date,
    v.source_product_id,
    tt.transaction_type_id,
    cf.finish_id,
    cc.condition_id,
    lr.language_id,
    dp.data_provider_id,
    v.price_cents,
    now()
FROM unnest($2::bigint[], $3::text[], $4::int[]) AS v(source_product_id, finish_code, price_cents)
JOIN pricing.transaction_type tt ON tt.transaction_type_code = 'sell'
JOIN card_catalog.card_finished cf ON cf.code = v.finish_code
JOIN pricing.card_condition cc ON cc.code = 'NM'
JOIN card_catalog.language_ref lr ON lr.language_code = 'en'
JOIN pricing.data_provider dp ON dp.code = 'scryfall'
ON CONFLICT (ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)
DO UPDATE SET
    list_avg_cents = EXCLUDED.list_avg_cents,
    scraped_at = EXCLUDED.scraped_at,
    updated_at = now()
"""


class PricingTierRepository(AbstractRepository):
    """Repository for pricing tier aggregation procedures."""

    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "PriceRepository"

    async def refresh_daily_prices(
        self,
        p_from: Optional[date] = None,
        p_to: Optional[date] = None,
    ) -> dict:
        """
        Populate Tier 2 (print_price_daily) from Tier 1 (price_observation).

        Links source_product_id → card_version_id via mtg_card_products.

        Args:
            p_from: Start date (inclusive). If None, uses last_processed_date from watermark.
            p_to: End date (inclusive). If None, uses CURRENT_DATE - 1.

        Returns:
            Dict with procedure output (notice messages, row counts).
        """
        try:
            await self.execute_procedure(
                "pricing.refresh_daily_prices",
                (p_from, p_to),
            )
            logger.info(
                "refresh_daily_prices completed",
                extra={"p_from": p_from, "p_to": p_to},
            )
            return {"status": "success"}
        except Exception as e:
            logger.error(
                "refresh_daily_prices failed",
                extra={"p_from": p_from, "p_to": p_to, "error": str(e)},
            )
            raise

    async def archive_to_weekly(
        self,
        older_than_interval: str = "5 YEARS",
    ) -> dict:
        """
        Archive Tier 2 (print_price_daily) rows to Tier 3 (print_price_weekly).

        Args:
            older_than_interval: PostgreSQL interval string (e.g., '5 YEARS', '90 DAYS').

        Returns:
            Dict with procedure output (notice messages, row counts).
        """
        try:
            # Convert string interval to proper SQL format
            interval_param = f"INTERVAL '{older_than_interval}'"
            await self.execute_procedure(
                "pricing.archive_to_weekly",
                (interval_param,),
            )
            logger.info(
                "archive_to_weekly completed",
                extra={"older_than_interval": older_than_interval},
            )
            return {"status": "success"}
        except Exception as e:
            logger.error(
                "archive_to_weekly failed",
                extra={"older_than_interval": older_than_interval, "error": str(e)},
            )
            raise

    async def upsert_scryfall_price_batch(
        self,
        rows: list[dict],  # [{scryfall_id, source_code, finish_code, price_cents}]
        ts_date: date,
    ) -> int:
        """Upsert a batch of Scryfall prices into pricing.price_observation.

        Steps:
          1. Resolve scryfall_ids → card_version_id + existing product_id.
          2. For cards with no product_id: create product_ref + mtg_card_products.
          3. Ensure source_product rows exist for all (product_id, source_code) pairs.
          4. Fetch source_product_ids.
          5. UPSERT into price_observation.

        Returns the number of rows upserted.
        """
        if not rows:
            return 0

        scryfall_ids = list({r["scryfall_id"] for r in rows})

        # Step 1 — Resolve scryfall_ids → card_version_id + product_id
        resolved = await self.connection.fetch(_RESOLVE_SCRYFALL_IDS_SQL, scryfall_ids)

        # Build lookup: scryfall_id → {card_version_id, product_id}
        scryfall_to_meta: dict[str, dict] = {}
        for rec in resolved:
            scryfall_to_meta[rec["scryfall_id"]] = {
                "card_version_id": rec["card_version_id"],
                "product_id": rec["product_id"],
            }

        # Step 2 — Batch-create product_ref + mtg_card_products for unlinked cards
        # Build a reverse map for efficient cv_id → scryfall_id lookup
        cv_id_to_sid: dict[str, str] = {
            str(meta["card_version_id"]): sid
            for sid, meta in scryfall_to_meta.items()
        }

        unlinked_cv_ids = [
            meta["card_version_id"]
            for meta in scryfall_to_meta.values()
            if meta["product_id"] is None
        ]
        if unlinked_cv_ids:
            new_rows = await self.connection.fetch(_INSERT_PRODUCTS_BATCH_SQL, unlinked_cv_ids)
            for row in new_rows:
                sid = cv_id_to_sid.get(str(row["card_version_id"]))
                if sid is not None:
                    scryfall_to_meta[sid]["product_id"] = row["product_id"]

            # Some cards may have had conflicts (product already existed) — fetch their IDs
            still_missing_cv_ids = [
                meta["card_version_id"]
                for meta in scryfall_to_meta.values()
                if meta["product_id"] is None
            ]
            if still_missing_cv_ids:
                existing = await self.connection.fetch(
                    _GET_PRODUCT_IDS_FOR_CARDS_SQL, still_missing_cv_ids
                )
                cv_to_product = {
                    str(row["card_version_id"]): row["product_id"] for row in existing
                }
                for meta in scryfall_to_meta.values():
                    cv_str = str(meta["card_version_id"])
                    if meta["product_id"] is None and cv_str in cv_to_product:
                        meta["product_id"] = cv_to_product[cv_str]

        # Step 3 — Ensure source_product rows exist
        # Build parallel arrays of (product_id, source_code) for all batch rows
        # where we have a resolved product_id.
        sp_product_ids: list = []
        sp_source_codes: list = []
        for r in rows:
            meta = scryfall_to_meta.get(r["scryfall_id"])
            if meta and meta["product_id"] is not None:
                sp_product_ids.append(str(meta["product_id"]))
                sp_source_codes.append(r["source_code"])

        if not sp_product_ids:
            return 0

        await self.connection.execute(
            _ENSURE_SOURCE_PRODUCT_SQL, sp_product_ids, sp_source_codes
        )

        # Step 4 — Fetch source_product_ids
        unique_product_ids = list(set(sp_product_ids))
        unique_source_codes = list(set(sp_source_codes))
        sp_rows = await self.connection.fetch(
            _FETCH_SOURCE_PRODUCT_IDS_SQL, unique_product_ids, unique_source_codes
        )

        # Build lookup: (product_id_str, source_code) → source_product_id
        sp_lookup: dict[tuple, int] = {}
        for sp in sp_rows:
            sp_lookup[(str(sp["product_id"]), sp["source_code"])] = sp["source_product_id"]

        # Step 5 — UPSERT into price_observation
        obs_source_product_ids: list[int] = []
        obs_finish_codes: list[str] = []
        obs_price_cents: list[int] = []

        for r in rows:
            meta = scryfall_to_meta.get(r["scryfall_id"])
            if not meta or meta["product_id"] is None:
                continue
            key = (str(meta["product_id"]), r["source_code"])
            sp_id = sp_lookup.get(key)
            if sp_id is None:
                continue
            obs_source_product_ids.append(sp_id)
            obs_finish_codes.append(r["finish_code"])
            obs_price_cents.append(r["price_cents"])

        if not obs_source_product_ids:
            return 0

        status = await self.connection.execute(
            _UPSERT_PRICE_OBSERVATION_SQL,
            ts_date,
            obs_source_product_ids,
            obs_finish_codes,
            obs_price_cents,
        )
        # status is like "INSERT 0 N"
        try:
            return int(status.split()[-1])
        except (IndexError, ValueError):
            return len(obs_source_product_ids)

    async def execute_procedure(self, proc_name: str, args: tuple) -> None:
        """
        Execute a stored procedure with arguments.

        Args:
            proc_name: Fully qualified procedure name (e.g., 'pricing.refresh_daily_prices')
            args: Tuple of arguments to pass to the procedure
        """
        # Build the CALL statement
        placeholders = ", ".join(f"${i+1}" for i in range(len(args)))
        call_stmt = f"CALL {proc_name}({placeholders})"

        # Execute via the connection
        await self.connection.execute(call_stmt, *args)
