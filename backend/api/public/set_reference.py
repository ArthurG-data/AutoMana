from fastapi import APIRouter, Query
from typing import List, Annotated
from backend.request_handling.ApiHandler import ApiHandler
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse
from uuid import UUID

router = APIRouter(
        prefix="/set-reference",
        tags=['sets'], 
        responses={404:{'description':'Not found'}}
        
)

@router.get('/{set_id}', response_model=ApiResponse)
async def get_set(set_id : UUID):
    return  await ApiHandler.execute_service("card_catalog.set.get", set_id=set_id)

@router.get('/', response_model=PaginatedResponse)
async def get_sets(
                    limit : Annotated[int, Query(le=100)]=100,
                    offset: int =0,
                    ids : Annotated[List[str],Query(title='Optional set_is')]=None):
     return  await ApiHandler.execute_service("card_catalog.set.list", limit=limit, offset=offset, ids=ids)

