from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from typing import List, Optional, Any
from automana.core.models.shopify import shopify_theme


class ShopifyCollectionRepository(AbstractRepository[shopify_theme.CollectionModel]):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "ShopifyCollectionRepository"

    async def add(self, values: shopify_theme.InsertCollection):
        await self.execute_command(
            """
            INSERT INTO markets.collection_handles (market_id, name)
            VALUES ($1, $2)
            ON CONFLICT (name, market_id) DO NOTHING;
            """,
            (values.market_id, values.name),
        )

    async def add_many(self, values: List[shopify_theme.InsertCollection]):
        if not values:
            return
        await self.execute_many(
            """
            INSERT INTO markets.collection_handles (name, market_id)
            VALUES ($1, $2)
            ON CONFLICT (name, market_id) DO NOTHING;
            """,
            [(v.name, v.market_id) for v in values],
        )

    async def get(self, name: str, market_id: int) -> Any | None:
        result = await self.execute_query(
            "SELECT * FROM markets.collection_handles WHERE name = $1 AND market_id = $2;",
            (name, market_id),
        )
        return result[0] if result else None

    async def link_collection_theme(self, values: shopify_theme.InsertCollectionTheme) -> Any:
        result = await self.execute_query(
            """
            INSERT INTO markets.handles_theme (handle_id, theme_id)
            SELECT ch.handle_id, cg.game_id
            FROM markets.collection_handles AS ch
            JOIN pricing.card_game AS cg ON cg.code = $2
            WHERE ch.name = $1
            ON CONFLICT (handle_id, theme_id) DO NOTHING
            RETURNING *;
            """,
            (values.collection_name, values.theme_code),
        )
        return result[0] if result else None

    async def list(self) -> List[Any]:
        rows = await self.connection.fetch("SELECT * FROM markets.collection_handles")
        return [dict(row) for row in rows] if rows else []

    async def add_theme(self, values: shopify_theme.InsertTheme):
        await self.execute_command(
            """
            INSERT INTO pricing.card_game (code, name)
            VALUES ($1, $2)
            ON CONFLICT (code) DO NOTHING;
            """,
            (values.code, values.name),
        )

    async def update(self, item: shopify_theme.CollectionModel) -> None:
        pass

    async def delete(self, id: int) -> None:
        pass
