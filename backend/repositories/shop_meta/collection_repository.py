from backend.repositories.AbstractRepository import AbstractRepository
from typing import List, Optional, Any
from backend.services_old.shop_data_ingestion.models import shopify_theme

class CollectionRepository(AbstractRepository[shopify_theme.CollectionModel]):
    def __init__(self, connection):
        super().__init__(connection)

    async def add(self, values: shopify_theme.InsertCollection):
        """Add a collection to the database"""
        await self.connection.execute(
            """
            INSERT INTO collections (name, market_id)
            VALUES ($1, $2)
            ON CONFLICT (name, market_id)
            DO NOTHING;
            """,
            values.name, values.market_id
        )

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

    async def get(self, id: int) -> Any | None:
        """Get a collection by ID"""
        result = await self.connection.fetchrow(
            """
            SELECT * FROM collections WHERE id = $1;
            """,
            id
        )
        return result if result else None

    async def list(self) -> List[Any]:
        """List all collections"""
        rows = await self.connection.fetch(
            "SELECT * FROM collections"
        )
        return [dict(row) for row in rows] if rows else []