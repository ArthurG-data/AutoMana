from backend.repositories.AbstractRepository import AbstractRepository
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
        

    async def fetch_all_prices(self):
        """
        Fetch all rows from the staging table for verification.
        """
        fetch_query = "SELECT * FROM str_mtg_stock_price;"
        try:
            rows = await self.execute_query(fetch_query)
            logger.info(f"Fetched {len(rows)} rows from str_mtg_stock_price.")
            return rows
        except Exception as e:
            logger.error(f"Error fetching data from str_mtg_stock_price: {e}")
            return []

    async def copy_prices(self, df):
        await self._copy_to_table(df, "str_mtg_stock_price")
        await self.connection.execute('COMMIT;')

    async def create_staging_table(self):
        """
        Create the staging table if it does not exist.
        """
        create_table_query = """
        CREATE TABLE IF NOT EXISTS str_mtg_stock_price (
            ts_date DATE NOT NULL,
            game_code TEXT NOT NULL,
            card_version_id UUID NOT NULL,
            price_low NUMERIC(12,4),
            price_avg NUMERIC(12,4),
            price_foil NUMERIC(12,4),
            price_market NUMERIC(12,4),
            price_market_foil NUMERIC(12,4),
            source_code TEXT NOT NULL
           --,scraped_at TIMESTAMPTZ DEFAULT now()
        );
        """
        await self.execute_command(create_table_query)

    async def drop_staging_table(self):
        """
        Drop the staging table if it exists.
        """
        drop_table_query = """
        DROP TABLE IF EXISTS str_mtg_stock_price;
        """
        await self.execute_command(drop_table_query)

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