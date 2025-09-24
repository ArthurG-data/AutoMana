from backend.repositories.AbstractRepository import AbstractRepository
from typing import List, Optional, Any
from backend.schemas.external_marketplace.shopify import Market as Market_Model
import io, logging

class ProductRepository(AbstractRepository):
    def __init__(self, connection, executor : None):
        super().__init__(connection, executor)


    @property
    def name(self) -> str:
        return "ProductShopifyRepository"
    
    async def _copy_to_table(self, df, table):
        buf = io.BytesIO()
        df.to_csv(buf, index=False, header=True, encoding='utf-8')
        buf.seek(0)
        await self.connection.copy_to_table(
            table,
            source=buf,
            format='csv',
            header=True)
    
    async def bulk_copy_prices(self, df):
        await self._copy_to_table(df, "raw_mtg_stock_price")
        await self.connection.execute('COMMIT;')

    async def bulk_insert_products(self, products: List[dict]):
        query = 'CALL add_product_batch_arrays(%s, %s, %s, %s, %s)'
        await self.execute_command(query, products)

    async def bulk_insert_prices(self, prices: List[dict]):
        query = """
        CALL add_price_batch_arrays(%s, %s, %s, %s, %s, %s, %s)
        """
        await self.execute_command(query, prices)

    async def insert_card_product_reference(self, values: dict):
        query = """
        CALL add_card_product_ref_batch(%s,%s,%s,%s);
        """
        await self.execute_command(query, values)
    
    async def add(self):
        raise NotImplementedError("Method not implemented yet")
    
    async def delete(self, id):
        raise NotImplementedError("Method not implemented yet")
    
    async def get(self, id) -> Optional[Any]:
        raise NotImplementedError("Method not implemented yet")
    
    async def list(self) -> List[Any]:
        raise NotImplementedError("Method not implemented yet")
    
    async def update(self, item):
        raise NotImplementedError("Method not implemented yet")
    
