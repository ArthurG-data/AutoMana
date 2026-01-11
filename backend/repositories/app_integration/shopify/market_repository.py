from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from typing import List, Optional, Any
from backend.schemas.external_marketplace.shopify import Market as Market_Model
from backend.repositories.app_integration.shopify import market_queries as queries

class MarketRepository(AbstractRepository):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "MarketShopifyRepository"

    async def add(self, values: Market_Model.InsertMarket):
        """Add a market to the database"""
        await self.execute_command(
            queries.insert_market_query,
            values.name, values.api_url, values.country_code, values.city
        )

    async def get_market_code(self, name: str) -> Optional[str]:
        """Get a market by name"""
        query = "SELECT source_id FROM price_source WHERE code = $1;"
        result = await self.execute_query(
            query,
            (name,)
        )
        return result[0].get('source_id') if result else None
    
    async def get(self, id: int) -> Market_Model.Market | None:
        """Get a market by ID"""
        result = await self.connection.fetchrow(
            queries.select_market_id_query,
            id
        )
        return result if result else None

    async def update(self, market: Market_Model.UpdateMarket):
        """Update a market in the database with null-safety"""
        # Start with base query parts
        query_parts = ["UPDATE markets SET"]
        values = [market.id]  # Start with the ID which we need for WHERE clause
        set_clauses = []
        
        # Only include non-None fields
        if market.country_code is not None:
            values.append(market.country_code)
            set_clauses.append(f"country_code = ${len(values)}")
            
        if market.city is not None:
            values.append(market.city)
            set_clauses.append(f"city = ${len(values)}")
            
        if market.api_url is not None:
            values.append(market.api_url)
            set_clauses.append(f"api_url = ${len(values)}")
        
        # If nothing to update, just return
        if not set_clauses:
            return
            
    # Construct the final query
        query = f"{query_parts[0]} {', '.join(set_clauses)} WHERE market_id = $1"
    
    # Execute the query
        await self.connection.execute(query, *values)

    async def delete(self, id: int):
        """Delete a market from the database"""
        await self.connection.execute(
            """
            DELETE FROM markets WHERE market_id = $1;
            """,
            id
        )
    
    async def list(
        self,
    ) -> List[Market_Model.MarketInDb]:
       
        rows = await self.connection.fetch(
            queries.select_all_markets_query
        )
        items = [Market_Model.MarketInDb(**dict(row)) for row in rows]
        return items
