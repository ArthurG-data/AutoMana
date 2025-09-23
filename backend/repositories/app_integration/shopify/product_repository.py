from backend.repositories.AbstractRepository import AbstractRepository
from typing import List, Optional, Any
from backend.schemas.external_marketplace.shopify import Market as Market_Model


class ProductRepository(AbstractRepository):
    def __init__(self, connection, executor : None):
        super().__init__(connection, executor)


    @property
    def name(self) -> str:
        return "ProductShopifyRepository"
    
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
