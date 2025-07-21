from fastapi import HTTPException
from typing import List,  Optional, Sequence
from uuid import UUID
from backend.modules.public.sets.utils import create_value
from backend.database.database_utilis import create_select_query
from backend.utils_new.card_catalog.create_value_set import create_value
from backend.repositories.card_catalog.set_repository import SetReferenceRepository
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.schemas.card_catalog.set import BaseSet, SetInDB, NewSet, UpdatedSet

async def get(repository: SetReferenceRepository, set_id: UUID) -> ApiResponse:
    values= create_value(set_id, False)
    result = await repository.get(values)
    if not result:
        return ApiResponse(status="error", message=f"Set with ID {set_id} not found")
    return ApiResponse(data=BaseSet.model_validate(result[0]))

async def list(repository: SetReferenceRepository, limit : Optional[int]=None, offset : Optional[int]=None, ids : Optional[List[UUID]]=None) ->  PaginatedResponse:
    results = await repository.list(limit=limit, offset=offset, ids=ids)
    sets = [BaseSet.model_validate(result) for result in results]
    return PaginatedResponse[BaseSet](
    data=sets,  # List of sets
    pagination=PaginationInfo(
        count=len(results),
        page=offset // limit + 1,
        pages=(len(results) + limit - 1) // limit,
        limit=limit
    )
)
    