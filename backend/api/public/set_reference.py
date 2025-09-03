from fastapi import APIRouter, Query, Depends, HTTPException
from typing import List, Annotated
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager
from backend.request_handling.StandardisedQueryResponse import (    ApiResponse
                                                                ,PaginatedResponse
                                                                ,ErrorResponse
                                                                ,PaginationInfo)
from uuid import UUID

router = APIRouter(
        prefix="/set-reference",
        tags=['sets'], 
        responses={
            404: {'description': 'Not found', 'model': ErrorResponse},
            500: {'description': 'Internal server error', 'model': ErrorResponse}
        }
)

@router.get('/{set_id}', response_model=ApiResponse)
async def get_set(set_id: UUID
                  , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        result = await service_manager.execute_service("card_catalog.set.get", set_id=set_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Set not found")
        
        return ApiResponse(
            success=True,
            data=result,
            message="Set retrieved successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/', response_model=PaginatedResponse)
async def get_sets(
                    limit: Annotated[int, Query(le=100)]=100,
                    offset: int=0,
                    ids: Annotated[List[str], Query(title='Optional set_ids')]=None,
                    service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        result = await service_manager.execute_service("card_catalog.set.get_all"
                                                       , limit=limit
                                                       , offset=offset
                                                       , ids=ids)
        return PaginatedResponse(
            success=True,
            data=result,
            message="Sets retrieved successfully",
            pagination=PaginationInfo(
                limit=limit,
                offset=offset,
                total_count=len(result),
                has_next=len(result) > limit,
                has_previous=offset > 0
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



