import logging
from typing import Optional
import pandas as pd
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_VARIATION_CONDITION_MAP = {
    "near mint":         "NM",
    "lightly played":    "LP",
    "slightly played":   "LP",
    "moderately played": "MP",
    "heavily played":    "HP",
    "damaged":           "DMG",
}


def _map_variation(variation: str) -> tuple[str, str]:
    """Return (condition_code, finish_code) from a Shopify variant title."""
    lower = variation.lower().strip()
    is_foil = lower.endswith(" foil")
    base = lower[: -len(" foil")].strip() if is_foil else lower
    condition = _VARIATION_CONDITION_MAP.get(base, "NM")
    finish = "foil" if is_foil else "nonfoil"
    return condition, finish


class ShopifyPipelineRepository(AbstractRepository):
    @property
    def name(self) -> str:
        return "ShopifyPipelineRepository"

    async def get_active_pipeline_markets(self) -> list[dict]:
        """Returns markets that have api_url AND source_id set, including price_source code."""
        rows = await self.connection.fetch(
            """
            SELECT mr.market_id, mr.name, mr.api_url, mr.country_code,
                   mr.source_id, ps.code AS source_code
            FROM markets.market_ref mr
            JOIN pricing.price_source ps ON ps.source_id = mr.source_id
            WHERE mr.api_url IS NOT NULL AND mr.source_id IS NOT NULL
            """
        )
        return [dict(r) for r in rows]

    async def upsert_product_handles(self, rows: list[dict]) -> None:
        """Upsert handle + title on markets.product_ref.
        Each dict must have: product_id (str), market_id (int), handle (str), title (str).
        """
        if not rows:
            return
        await self.execute_many(
            """
            INSERT INTO markets.product_ref (product_shop_id, product_id, market_id, handle, title)
            VALUES ($1, $1, $2, $3, $4)
            ON CONFLICT (product_shop_id)
            DO UPDATE SET handle = EXCLUDED.handle,
                          title  = EXCLUDED.title,
                          updated_at = NOW()
            """,
            [(str(r["product_id"]), r["market_id"], r.get("handle"), r.get("title")) for r in rows],
        )

    async def find_card_versions_by_tcg_ids(self, tcg_ids: list[int]) -> dict[int, str]:
        """Map tcg_id -> card_version_id (UUID as str). Unmapped IDs are omitted."""
        if not tcg_ids:
            return {}
        rows = await self.connection.fetch(
            """
            SELECT cei.value::BIGINT AS tcg_id, cei.card_version_id::TEXT
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
                ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
               AND cir.identifier_name = 'tcgplayer_id'
            WHERE cei.value::BIGINT = ANY($1::BIGINT[])
            """,
            tcg_ids,
        )
        return {r["tcg_id"]: r["card_version_id"] for r in rows}

    async def bootstrap_source_products(
        self, card_version_ids: list[str], source_id: int
    ) -> dict[str, int]:
        """Ensure product_ref + mtg_card_products + source_product rows exist for each
        card_version_id/source_id pair. Returns {card_version_id: source_product_id}.

        Uses a CTE so the generated UUID is shared between the product_ref and
        mtg_card_products inserts in one statement — avoids the broken-join problem
        where a second statement can't find the product_id it just created.
        """
        if not card_version_ids:
            return {}

        # Create product_ref + mtg_card_products in one statement via shared CTE UUID.
        # Matches the canonical pattern in 06_prices.sql:2083-2104.
        await self.connection.execute(
            """
            WITH need AS (
                SELECT cv.card_version_id
                FROM unnest($1::UUID[]) AS cv(card_version_id)
                WHERE NOT EXISTS (
                    SELECT 1 FROM pricing.mtg_card_products mcp
                    WHERE mcp.card_version_id = cv.card_version_id
                )
            ),
            gen AS (
                SELECT card_version_id, uuid_generate_v4() AS product_id
                FROM need
            ),
            ins_prod AS (
                INSERT INTO pricing.product_ref (product_id, game_id)
                SELECT g.product_id, cg.game_id
                FROM gen g
                JOIN pricing.card_game cg ON cg.code = 'mtg'
                ON CONFLICT (product_id) DO NOTHING
            )
            INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
            SELECT product_id, card_version_id
            FROM gen
            ON CONFLICT (card_version_id) DO NOTHING
            """,
            card_version_ids,
        )

        # Ensure source_product rows for this source_id
        await self.connection.execute(
            """
            INSERT INTO pricing.source_product (product_id, source_id)
            SELECT mcp.product_id, $2
            FROM unnest($1::UUID[]) AS cv(card_version_id)
            JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
            ON CONFLICT (product_id, source_id) DO NOTHING
            """,
            card_version_ids,
            source_id,
        )

        rows = await self.connection.fetch(
            """
            SELECT mcp.card_version_id::TEXT, sp.source_product_id
            FROM unnest($1::UUID[]) AS cv(card_version_id)
            JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
            JOIN pricing.source_product sp
                ON sp.product_id = mcp.product_id AND sp.source_id = $2
            """,
            card_version_ids,
            source_id,
        )
        return {r["card_version_id"]: r["source_product_id"] for r in rows}

    async def bulk_copy_observations(self, df: pd.DataFrame) -> int:
        """Insert DataFrame rows into pricing.price_observation idempotently.
        Uses ON CONFLICT DO NOTHING so re-runs on the same ts_date are safe.
        Returns row count attempted (some may be skipped as duplicates).
        """
        if df.empty:
            return 0
        records = [
            (
                r["ts_date"], r["price_type_id"], r["finish_id"], r["condition_id"],
                r["language_id"], r["list_low_cents"], r["list_avg_cents"],
                r["sold_avg_cents"], r["list_count"], r["sold_count"],
                r["source_product_id"], r["data_provider_id"], r["scraped_at"],
            )
            for r in df.to_dict("records")
        ]
        await self.execute_many(
            """
            INSERT INTO pricing.price_observation
                (ts_date, price_type_id, finish_id, condition_id, language_id,
                 list_low_cents, list_avg_cents, sold_avg_cents, list_count, sold_count,
                 source_product_id, data_provider_id, scraped_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT DO NOTHING
            """,
            records,
        )
        return len(df)

    async def truncate_staging(self) -> None:
        await self.connection.execute("TRUNCATE pricing.shopify_staging_raw;")

    async def get_staging_rows(self) -> list[dict]:
        """Fetch all staged rows for promote step."""
        rows = await self.connection.fetch(
            """
            SELECT product_id, date, variation, price, scraped_at, tcg_id, source_id
            FROM pricing.shopify_staging_raw
            WHERE tcg_id IS NOT NULL AND source_id IS NOT NULL
            """
        )
        return [dict(r) for r in rows]

    async def get_reference_ids(self) -> dict:
        """Fetch static reference IDs needed to build price_observation rows."""
        sell_type = await self.connection.fetchrow(
            "SELECT transaction_type_id FROM pricing.transaction_type WHERE transaction_type_code = 'sell'"
        )
        dp = await self.connection.fetchrow(
            "SELECT data_provider_id FROM pricing.data_provider WHERE code = 'shopify'"
        )
        lang = await self.connection.fetchrow(
            "SELECT language_id FROM card_catalog.language_ref WHERE language_code = 'en'"
        )
        conditions = await self.connection.fetch(
            "SELECT code, condition_id FROM pricing.card_condition"
        )
        finishes = await self.connection.fetch(
            "SELECT code, finish_id FROM card_catalog.card_finished"
        )
        return {
            "sell_type_id": sell_type["transaction_type_id"],
            "data_provider_id": dp["data_provider_id"],
            "language_id": lang["language_id"],
            "conditions": {r["code"]: r["condition_id"] for r in conditions},
            "finishes": {r["code"].lower(): r["finish_id"] for r in finishes},
        }

    async def add(self): raise NotImplementedError
    async def delete(self, id): raise NotImplementedError
    async def get(self, id): raise NotImplementedError
    async def list(self): raise NotImplementedError
    async def update(self, item): raise NotImplementedError
