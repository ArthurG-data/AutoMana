from backend.repositories.AbstractRepository import AbstractRepository
from typing import List, Optional, Any

class ShopifyPriceRepository(AbstractRepository[shopify_theme.CollectionModel]):
    def __init__(self,queryExecutor, connection):
        super().__init__(connection, queryExecutor)
    
    def name(self) -> str:
        return "ShopifyPriceRepository"
    
    async def bulk_insert_product(self, values):
        query = 'CALL add_product_batch_arrays(%s, %s, %s, %s, %s)'
        await self.execute_command(query, (values,))

    
    async def bulk_insert_prices(self, values):
        
        query = """
        CALL add_price_batch_arrays(%s, %s, %s, %s, %s, %s, %s)
        """
        await self.execute_command(query, (values,))

