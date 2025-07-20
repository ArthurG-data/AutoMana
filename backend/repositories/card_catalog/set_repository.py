from backend.request_handling.StandardisedQueryResponse import ApiResponse
from backend.repositories.AbstractRepository import AbstractRepository
from backend.database.database_utilis import create_select_query
from typing import Any, Optional, Sequence
from uuid import UUID

class SetReferenceRepository(AbstractRepository[Any]):
    def __init__(self, connection, executor: None):
        super().__init__(connection, executor)

    def name(self) -> str:
        return "SetReferenceRepository"

    async def add(self, value: CreateSet):
        await self.execute_command(queries.insert_set_query, (value,))

    async def add_many(self, values: CreateSets):
        await self.execute_command(queries.insert_set_query, values)

    async def delete(self, set_id: UUID):
        result = await self.execute_command(queries.delete_set_query, set_id)
        return result is not None

    async def update(self, item):
        pass

    async def get(self, set_id: UUID) -> ApiResponse:
        query = create_select_query('joined_set_materialized', conditions_list=["set_id = %s"])
        return await self.execute_query(query, (set_id,))
    
    async def list(self, sets_ids: Optional[Sequence[UUID]] = None, limit: int = 100, offset: int = 0):

        if sets_ids:
            query =  create_select_query('joined_set_materialized', conditions_list=["set_id = ANY($1)"], limit=limit, offset=offset)
            values = ((sets_ids, ),limit, offset)
        else:
            query = create_select_query('joined_set_materialized', limit=limit, offset=offset)
            values = (limit, offset)
        return await self.execute_query(query, values)