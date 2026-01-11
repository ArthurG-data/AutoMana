from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
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

    async def _copy_to_table(self, df, table):
        buf = io.BytesIO()
        df.to_csv(buf, index=False, header=True, encoding='utf-8')
        buf.seek(0)
        await self.connection.copy_to_table(
            table,
            source=buf,
            format='csv',
            header=True)

    async def call_load_stage_from_raw(self):
        """
        Call the load_staging_prices procedure.
        """
        await self.connection.execute("CALL load_staging_prices();")

    async def call_load_dim_from_staging(self):
        """
        Call the load_dim_from_staging procedure.
        """
        await self.connection.execute("CALL load_dim_from_staging();")

    async def call_load_prices_from_dim(self):
        """
        Call the load_prices_from_dim procedure.
        """
        def _on_notify(conn, pid, channel, payload):
            logger.info("DB notify %s: %s", channel, payload)

        try:
            # register listener
            await self.connection.add_listener('staging_log', _on_notify)
            # call the procedure (must be a PROCEDURE)
            await self.connection.execute("CALL load_prices_from_dim();")
            logger.info("Called load_prices_from_dim()")
        finally:
            # remove listener
            try:
                await self.connection.remove_listener('staging_log', _on_notify)
            except Exception:
                pass

    async def fetch_all_prices(self, table_name):
        """
        Fetch all rows from the staging table for verification.
        """
        fetch_query = f"SELECT COUNT(*) FROM {table_name};"
        try:
            count = await self.execute_query(fetch_query)
            logger.info(f"Fetched {count} rows from {table_name}.")
            return count
        except Exception as e:
            logger.error(f"Error fetching data from {table_name}: {e}")
            return 0

    async def copy_prices(self, df):
        await self._copy_to_table(df, "shopify_staging_raw")
        await self.connection.execute('COMMIT;')

    
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