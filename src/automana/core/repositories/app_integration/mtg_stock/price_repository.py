from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
import io, logging
from typing import Optional

logger = logging.getLogger(__name__)

class PriceRepository(AbstractRepository):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "PriceRepository"

    async def rollback_transaction(self):
        """
        Roll back the current transaction.
        """
        try:
            await self.connection.execute("ROLLBACK;")
            logger.info("Transaction rolled back successfully.")
        except Exception as e:
            logger.error("Error rolling back transaction: %s", e)

    async def _copy_to_table(self, df, schema_name, table_name):
        buf = io.BytesIO()
        df.to_csv(buf, index=False, header=True, encoding='utf-8')
        buf.seek(0)
        await self.connection.copy_to_table(
            table_name=table_name,
            schema_name=schema_name,
            source=buf,
            format='csv',
            header=True)

    async def call_load_stage_from_raw(self, source_name: str = "mtgstocks", batch_days: int = 30):
        """Call pricing.load_staging_prices_batched(source_name, batch_days).

        `source_name` must match a row in `pricing.price_source.code`. Migration
        16 made `source_name` a required positional argument."""
        await self.connection.execute(
            "CALL pricing.load_staging_prices_batched($1::varchar, $2::int);",
            source_name,
            batch_days,
        )

    async def call_resolve_price_rejects(
        self,
        limit: int = 50000,
        only_unresolved: bool = True,
    ) -> int:
        """Invoke pricing.resolve_price_rejects(p_limit, p_only_unresolved).

        Note: `resolve_price_rejects` is a FUNCTION (returns bigint), not a
        procedure — invoke with SELECT. Returns the number of reject rows
        it was able to resolve and re-feed into staging."""
        row = await self.connection.fetchrow(
            "SELECT pricing.resolve_price_rejects($1::int, $2::boolean) AS rows_resolved;",
            limit,
            only_unresolved,
        )
        return int(row["rows_resolved"] or 0) if row else 0

    async def call_load_prices_from_staging(self, batch_days: int = 30):
        """Call pricing.load_prices_from_staged_batched(batch_days).

        Promotes narrow rows from `pricing.stg_price_observation` into the
        `pricing.price_observation` hypertable. Replaces the legacy pair
        `load_dim_from_staging` + `load_prices_from_dim_batched` which were
        never created in the live DB."""
        def _on_notify(conn, pid, channel, payload):
            logger.info("DB notify %s: %s", channel, payload)

        try:
            await self.connection.add_listener('staging_log', _on_notify)
            await self.connection.execute(
                "CALL pricing.load_prices_from_staged_batched($1::int);",
                batch_days,
            )
            logger.info("Called load_prices_from_staged_batched()")
        finally:
            try:
                await self.connection.remove_listener('staging_log', _on_notify)
            except Exception:
                pass

    async def fetch_all_prices(self, schema_name, table_name):
        """
        Fetch all rows from the staging table for verification.
        """
        fetch_query = f"SELECT COUNT(*) FROM {schema_name}.{table_name};"
        try:
            count = await self.execute_query(fetch_query)
            logger.info(f"Fetched {count} rows from {schema_name}.{table_name}.")
            return count
        except Exception as e:
            logger.error(f"Error fetching data from {schema_name}.{table_name}: {e}")
            return 0

    async def copy_prices(self, df):
        await self._copy_to_table(df, "pricing", "shopify_staging_raw")

    async def copy_prices_mtgstock(self, df):
        await self._copy_to_table(df, "pricing", "raw_mtg_stock_price")

    # ------------------------------------------------------------------
    # Metric-registry primitives
    # ------------------------------------------------------------------
    # Read-only primitives used by mtgstock sanity-report metrics. First
    # four operate on the *current state* of the pricing staging tables —
    # `raw_mtg_stock_price` has no `ingestion_run_id` column, and staging
    # tables are repopulated per-run, so "current state after the most
    # recent run" is the only meaningful run-scope here (mirrors
    # `ops.integrity.scryfall_run_diff`).

    async def fetch_raw_prints_count(self) -> int:
        """Distinct print_id count currently in `pricing.raw_mtg_stock_price`."""
        query = """
        SELECT COUNT(DISTINCT print_id)::int AS n
        FROM pricing.raw_mtg_stock_price
        """
        rows = await self.execute_query(query)
        return rows[0]["n"] if rows else 0

    async def fetch_raw_rows_count(self) -> int:
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.raw_mtg_stock_price
        """
        rows = await self.execute_query(query)
        return rows[0]["n"] if rows else 0

    async def fetch_linked_count(self) -> int:
        """Staged rows resolved to a card_version_id."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.stg_price_observation
        WHERE card_version_id IS NOT NULL
        """
        rows = await self.execute_query(query)
        return rows[0]["n"] if rows else 0

    async def fetch_rejected_count(self) -> int:
        """Rows that failed resolution and landed in the reject table."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.stg_price_observation_reject
        """
        rows = await self.execute_query(query)
        return rows[0]["n"] if rows else 0

    async def fetch_promoted_count(
        self, since, until, source_code: str = "mtgstocks"
    ) -> int:
        """Count rows promoted to the `price_observation` hypertable inside a
        run's wall-clock window.

        Filters on `scraped_at` (timestamptz) — not `ts_date` (business date),
        which is the date the price applies to, unrelated to when the row
        was ingested. `scraped_at` is set by `bulk_load` at insertion time.
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.price_observation
        WHERE scraped_at >= $1
          AND scraped_at <= $2
          AND source_code = $3
        """
        rows = await self.execute_query(query, (since, until, source_code))
        return rows[0]["n"] if rows else 0

    async def fetch_max_observation_age_days(self) -> int | None:
        """Days since the most recent price_observation.ts_date across all sources."""
        query = """
        SELECT (CURRENT_DATE - MAX(ts_date))::int AS age_days
        FROM pricing.price_observation
        """
        rows = await self.execute_query(query, ())
        return rows[0]["age_days"] if rows else None

    async def fetch_per_source_lag_hours(self) -> dict[str, float | None]:
        """{source_code: hours_since_latest_observation} for every price_source."""
        query = """
        SELECT
            ps.code AS source_code,
            EXTRACT(EPOCH FROM (now() - MAX(po.created_at))) / 3600.0 AS lag_hours
        FROM pricing.price_source ps
        LEFT JOIN pricing.source_product sp ON sp.source_id = ps.source_id
        LEFT JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
        GROUP BY ps.code
        """
        rows = await self.execute_query(query, ())
        return {r["source_code"]: r["lag_hours"] for r in rows}

    async def fetch_per_source_observation_coverage_pct(
        self, window_days: int = 30
    ) -> dict[str, float | None]:
        """{source_code: pct} where pct is fraction of source_product rows with a
        price_observation in the last ``window_days`` days."""
        query = """
        SELECT
            ps.code AS source_code,
            CASE WHEN COUNT(sp.source_product_id) = 0 THEN NULL
                 ELSE ROUND(
                     100.0 * COUNT(DISTINCT po.source_product_id)
                     / NULLIF(COUNT(DISTINCT sp.source_product_id), 0), 2
                 )::float
            END AS pct
        FROM pricing.price_source ps
        LEFT JOIN pricing.source_product sp ON sp.source_id = ps.source_id
        LEFT JOIN pricing.price_observation po
               ON po.source_product_id = sp.source_product_id
              AND po.ts_date >= CURRENT_DATE - ($1::int || ' days')::interval
        GROUP BY ps.code
        """
        rows = await self.execute_query(query, (window_days,))
        return {r["source_code"]: r["pct"] for r in rows}

    async def fetch_orphan_product_ref_mtg_count(self) -> int:
        """pricing.product_ref rows whose game_id matches the 'mtg' card_game row
        but have no pricing.mtg_card_products row."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.product_ref pr
        JOIN pricing.card_game cg ON cg.game_id = pr.game_id
        WHERE cg.code = 'mtg'
          AND NOT EXISTS (
              SELECT 1 FROM pricing.mtg_card_products mcp
              WHERE mcp.product_id = pr.product_id
          )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_orphan_observation_count(self) -> int:
        """price_observation rows whose source_product_id no longer exists in
        source_product. Hard FK should make this 0."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.price_observation po
        WHERE NOT EXISTS (
            SELECT 1 FROM pricing.source_product sp
            WHERE sp.source_product_id = po.source_product_id
        )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_stg_residual_count(self) -> int:
        """Estimated row count of stg_price_observation via pg_class.reltuples.
        Fast (no scan); good enough for a residual-drain alarm."""
        query = """
        SELECT reltuples::bigint AS n
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'pricing' AND c.relname = 'stg_price_observation'
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_observation_pk_collision_count(self) -> int:
        """Composite-PK violations in price_observation. Should always be 0."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM (
            SELECT 1
            FROM pricing.price_observation
            GROUP BY ts_date, source_product_id, price_type_id, finish_id,
                     condition_id, language_id, data_provider_id
            HAVING COUNT(*) > 1
        ) dup
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    def add(self):
        raise NotImplementedError("Method not implemented")

    def delete(self):
        raise NotImplementedError("Method not implemented")

    def update(self):
        raise NotImplementedError("Method not implemented")
    def get(self):
        raise NotImplementedError("Method not implemented")

    async def list(self):
        raise NotImplementedError("Method not implemented")
