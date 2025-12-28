from backend.schemas.external_marketplace.shopify.shopify_theme import Theme, InsertTheme, DeleteTheme, UpdateTheme, ThemeWithId, ThemeList
from backend.repositories.AbstractRepository import AbstractRepository
from typing import Optional
class ThemeRepository(AbstractRepository[Theme]):
    def __init__(self, connection):
        super().__ini__(connection)

    async def add(self, theme: InsertTheme):
        """Add a theme to the database"""
        await self.conn.execute(
            """
            INSERT INTO theme_ref (code, name)
            VALUES ($1, $2)
            ON CONFLICT (code) DO NOTHING;
            """,
            theme.code, theme.name
        )
    async def delete_theme(self, theme : DeleteTheme):
        """Delete a theme from the database"""
        await self.conn.execute(
            """
            DELETE FROM theme_ref
            WHERE code = $1;
            """,
            theme.code
        )
    async def get_theme(self, theme: Theme) -> Optional[ThemeList]:
        """Get the theme_id for a given theme code"""
        result = await self.conn.fetchrow(
            """
            SELECT theme_id FROM theme_ref WHERE code = $1;
            """,
            theme.code
        )
        if result:
            return result['theme_id']
        else:
            raise ValueError(f"Theme '{theme.code}' not found.") 
        
    async def update_theme(self, theme: UpdateTheme):
        """Update a theme in the database"""
        await self.conn.execute(
            """
            UPDATE theme_ref
            SET name = $2
            WHERE code = $1;
            """,
            theme.code, theme.name
        )

class ShopMetaDataRepository:

    def __init__(self, connection):
        self.conn = connection

    async def add_collection(self, market_id: int, name: str):
        """Add a collection to the database"""
        await self.conn.execute(
            """
            INSERT INTO collection_handles (market_id, name)
            VALUES ($1, $2)
            ON CONFLICT (market_id, name) DO NOTHING;
            """,
            market_id, name
        )
    async def link_collection_theme(self, collection_name: str, theme_code: str):
        """Link a collection to a theme"""
        await self.conn.execute(
            """
            INSERT INTO handles_theme (handle_id, theme_id)
            SELECT
              ch.handle_id,
              tr.theme_id
            FROM
              collection_handles AS ch
              JOIN theme_ref AS tr ON TRUE
            WHERE
              ch.name = $1
              AND tr.code = $2
            ON CONFLICT (handle_id, theme_id) DO NOTHING;
            """,
            collection_name, theme_code
        )
   
    async def delete_collection(self, market_name: str, name: str):
        """Delete a collection from the database"""
        await self.conn.execute(
            """
            DELETE FROM collection_handles
            WHERE market_id = (SELECT market_id FROM market_ref WHERE name = $1)
            AND name = $2;
            """,
            market_name, name
        )
    async def delete_collection_theme(self, collection_name: str, theme_code: str):
        """Delete a collection-theme link"""
        await self.conn.execute(
            """
            DELETE FROM handles_theme
            WHERE handle_id = (SELECT handle_id FROM collection_handles WHERE name = $1)
            AND theme_id = (SELECT theme_id FROM theme_ref WHERE code = $2);
            """,
            collection_name, theme_code
        )
    async def get_market_id(self, name: str) -> int:
        """Get the market_id for a given market name"""
        result = await self.conn.fetchrow(
            """
            SELECT market_id FROM market_ref WHERE name = $1;
            """,
            name
        )
        if result:
            return result['market_id']
        else:
            raise ValueError(f"Market '{name}' not found.")
     
    async def get_theme_id(self, code: str) -> int:
        """Get the theme_id for a given theme code"""
        result = await self.conn.fetchrow(
            """
            SELECT theme_id FROM theme_ref WHERE code = $1;
            """,
            code
        )
        if result:
            return result['theme_id']
        else:
            raise ValueError(f"Theme '{code}' not found.")
    
    async def get_collection_id(self, market_id: int, name: str) -> int:
        """Get the collection_id for a given market_id and collection name"""
        result = await self.conn.fetchrow(
            """
            SELECT handle_id FROM collection_handles WHERE market_id = $1 AND name = $2;
            """,
            market_id, name
        )
        if result:
            return result['handle_id']
        else:
            raise ValueError(f"Collection '{name}' not found for market ID {market_id}.")
        
    async def get_collection_theme_id(self, collection_name: str, theme_code: str) -> int:
        """Get the collection-theme link ID for a given collection name and theme code"""
        result = await self.conn.fetchrow(
            """
            SELECT handle_id, theme_id FROM handles_theme
            WHERE handle_id = (SELECT handle_id FROM collection_handles WHERE name = $1)
            AND theme_id = (SELECT theme_id FROM theme_ref WHERE code = $2);
            """,
            collection_name, theme_code
        )
        if result:
            return result['handle_id'], result['theme_id']
        else:
            raise ValueError(f"No link found between collection '{collection_name}' and theme '{theme_code}'.")
'''
    async def batch_insert_collections(self, collections: list[shopify_models.InsertCollection]):
        """Insert multiple collections in a single batch"""
        async with self.conn.transaction():
            for collection in collections:
                await self.add_collection(collection.market_id, collection.name)
'''            