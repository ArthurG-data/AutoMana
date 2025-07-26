from typing import  Optional, Any, Sequence
from uuid import UUID
from fastapi import Query

from backend.repositories.AbstractRepository import AbstractRepository
from backend.schemas.card_catalog.card import CreateCard, CreateCards
from backend.repositories.card_catalog import card_queries as queries 
from backend.request_handling.StandardisedQueryResponse import ApiResponse

class CardReferenceRepository(AbstractRepository[Any]):
    def __init__(self, connection, executor : None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "CardRepository"
    
    async def add(self, value : CreateCard):
       await self.execute_command(queries.insert_full_card_query, (value,))

    async def add_many(self, values : CreateCards ):
        await self.execute_command(queries.insert_full_card_query, values)

    async def delete(self, card_id: UUID):
        result = await self.execute_command(queries.delete_card_query, card_id)
        return result is not None

    async def update(self, item):
        pass

    async def get(self,
                  card_id: UUID,
                 ) -> ApiResponse:
        # if a list
    
        query = """ SELECT uc.card_name, r.rarity_name, s.set_name,s.set_code, uc.cmc, cv.oracle_text, s.released_at, s.digital, r.rarity_name
                FROM unique_cards_ref uc
                JOIN card_version cv ON uc.unique_card_id = cv.unique_card_id
                JOIN rarities_ref r ON cv.rarity_id = r.rarity_id
                JOIN sets s ON cv.set_id = s.set_id 
                WHERE cv.card_version_id = $1;"""

        return await self.execute_query(query, (card_id,))

    async def list(self, card_ids: Optional[Sequence[UUID]] = None, limit: int = 100, offset: int = 0) -> ApiResponse:
        """List all card references"""
        values = (limit, offset)
        query = """ SELECT uc.card_name, r.rarity_name, s.set_name,s.set_code, uc.cmc, cv.oracle_text, s.released_at, s.digital, r.rarity_name
                FROM unique_cards_ref uc
                JOIN card_version cv ON uc.unique_card_id = cv.unique_card_id
                JOIN rarities_ref r ON cv.rarity_id = r.rarity_id
                JOIN sets s ON cv.set_id = s.set_id """
        if card_ids:
            query += "WHERE cv.card_version_id = ANY($1) LIMIT $2 OFFSET $3;"
            values = ((card_ids,), limit, offset)
        else:
            query += "LIMIT $1 OFFSET $2;"
        query += ";"
        return await self.execute_query(query, values)