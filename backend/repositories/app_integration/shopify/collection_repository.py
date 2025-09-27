from backend.repositories.AbstractRepository import AbstractRepository
from typing import List, Optional, Any
from backend.schemas.external_marketplace.shopify import shopify_theme

class ShopifyCollectionRepository(AbstractRepository[shopify_theme.CollectionModel]):
    def __init__(self,queryExecutor, connection):
        super().__init__(connection, queryExecutor)
    
    def name(self) -> str:
        return "ShopifyCollectionRepository"

    async def add(self, values: shopify_theme.InsertCollection):
        """Add a collection to the database"""
    
        query = """
            INSERT INTO collection_handles (market_id, name)
            VALUES (SELECT market_id FROM market_ref WHERE name = %s), %s
            ON CONFLICT (name) DO NOTHING;
            """
        
        self.execute_command(query,(values.market_id, values.name) )

    async def add_many(self, values: List[shopify_theme.InsertCollection]):
        """Add multiple collections to the database"""
        if not values:
            return
        query = """
            INSERT INTO collections (name, market_id)
            VALUES ($1, $2)
            ON CONFLICT (name, market_id)
            DO NOTHING;
        """
        await self.connection.executemany(query, [(v.name, v.market_id) for v in values])

    async def get(self, id: int, market_id: int) -> Any | None:
        """Get a collection by ID"""
        result = await self.execute_query(
            """
            SELECT * FROM collections WHERE id = $1 AND market_id = $2;
            """,
            id, market_id
        )
        return result if result else None
    
    async def link_collection_theme(self, values : shopify_theme.InsertCollectionTheme) -> Any:
        """Link a collection to a theme"""
        result = await self.execute_command(
            """
            INSERT INTO handles_theme (handle_id, theme_id)
            SELECT ch.handle_id, tr.theme_id
            FROM collection_handles AS ch
            JOIN theme_ref AS tr ON TRUE
            WHERE ch.name = $1 AND tr.code = $2
            ON CONFLICT (handle_id, theme_id) DO NOTHING
            RETURNING *;
            """,
            (values.collection_name, values.theme_code)
        )
        return result if result else None

    async def list(self) -> List[Any]:
        """List all collections"""
        rows = await self.connection.fetch(
            "SELECT * FROM collections"
        )
        return [dict(row) for row in rows] if rows else []
    
    async def add_theme(self, values : shopify_theme.InsertTheme):
        query = """
            INSERT INTO theme_ref (code, name)
            VALUES (%s, %s)
            ON CONFLICT (code) DO NOTHING;
            """
        await self.execute_command(query, (values.code, values.name))

        