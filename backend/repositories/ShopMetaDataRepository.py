from backend.services.shop_data_ingestion.models import shopify_models

class ShopMetaDataRepository:

    def __init__(self, connection):
        self.conn = connection

    async def add_theme(self, theme: shopify_models.InsertTheme):
        """Add a theme to the database"""
        await self.conn.execute(
            """
            INSERT INTO theme_ref (code, name)
            VALUES ($1, $2)
            ON CONFLICT (code) DO NOTHING;
            """,
            theme.code, theme.name
        )
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
     

            