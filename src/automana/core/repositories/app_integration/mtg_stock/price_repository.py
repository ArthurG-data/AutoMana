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
