from fastapi import APIRouter, Query, Depends
from typing import List, Annotated
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse
from uuid import UUID

router = APIRouter(
        prefix="/set-reference",
        tags=['sets'], 
        responses={404:{'description':'Not found'}}
        
)

@router.get('/{set_id}', response_model=ApiResponse)
async def get_set(set_id: UUID, service_manager: ServiceManager = Depends(get_service_manager)):
    return await service_manager.execute_service("card_catalog.set.get", set_id=set_id)

@router.get('/', response_model=PaginatedResponse)
async def get_sets(
                    limit: Annotated[int, Query(le=100)]=100,
                    offset: int=0,
                    ids: Annotated[List[str], Query(title='Optional set_is')]=None,
                    service_manager: ServiceManager = Depends(get_service_manager)):
     return await service_manager.execute_service("card_catalog.set.list", limit=limit, offset=offset, ids=ids)

