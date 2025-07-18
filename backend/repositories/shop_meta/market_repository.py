from backend.repositories.AbstractRepository import AbstractRepository
from typing import List, Optional, Any
from backend.services.shop_data_ingestion.models.shopify_models import Market as Market_Model

class MarketRepository(AbstractRepository[Market_Model.Market]):
    def __init__(self, connection):
        super().__init__(connection)

    async def add(self, market: Market_Model.InsertMarket):
        """Add a market to the database"""
        await self.connection.execute(
            """
            INSERT INTO markets (name, api_url, country_code, city)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (name, city, country_code) DO NOTHING;
            """,
            (market.name, market.api_url, market.country_code, market.city)
        )

    async def get(self, id: int) -> Market_Model.Market | None:
        """Get a market by ID"""
        result = await self.connection.fetchrow(
            """
            SELECT * FROM markets WHERE market_id = $1;
            """,
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
    
    def list(
        self,
    ) :
        sql = "SELECT market_id, name, api_url, country_code FROM market_ref"
       
        rows = self.execute_query(
            sql
        )
        return rows
    