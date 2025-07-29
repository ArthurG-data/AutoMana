from backend.request_handling.StandardisedQueryResponse import ApiResponse
from backend.repositories.AbstractRepository import AbstractRepository
from typing import Any, Optional, Sequence
from uuid import UUID
from backend.schemas.card_catalog.set import NewSet
import logging

logger = logging.getLogger(__name__)

class SetReferenceRepository(AbstractRepository[Any]):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "SetReferenceRepository"

    async def add(self, value: NewSet):
        raise NotImplementedError("Single insert not implemented for SetReferenceRepository")

    async def add_many(self, values: Sequence[NewSet]):
        raise NotImplementedError("Bulk insert not implemented for SetReferenceRepository")

    async def delete(self, set_id: UUID):
        raise NotImplementedError("Bulk insert not implemented for SetReferenceRepository")

    async def update(self, item):
        raise NotImplementedError("Bulk insert not implemented for SetReferenceRepository")

    async def get(self, set_id: UUID) -> ApiResponse:
        query = create_select_query('joined_set_materialized', conditions=["set_id = $1"])
        return await self.execute_query(query, set_id)
    
    async def list(self, limit: int = 100, offset: int = 0, ids: Optional[Sequence[UUID]] = None):
        query = "SELECT * FROM joined_set_materialized"
        counter = 1
        values = (limit, offset)
        if ids:
            query += f" WHERE set_id = ANY(${counter})"
            counter +=1
            values = ((ids, ), limit, offset)
        query += f" LIMIT ${counter} OFFSET ${counter + 1}"
        values = (limit, offset)
        logger.debug(f"Executing query: {query} with values: {values}")
        return await self.execute_query(query, values)