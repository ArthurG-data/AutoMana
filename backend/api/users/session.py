from fastapi import APIRouter, Depends,  HTTPException, Request, Response, status
from uuid import UUID
from backend.dependancies.service_deps import get_service_manager, get_current_active_user
from backend.dependancies.general import ipDep
from backend.new_services.service_manager import ServiceManager
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse,PaginationInfo

from backend.dependancies.query_deps import (
    session_search_params,
    pagination_params,
    sort_params,
    date_range_params,
    PaginationParams,
    SortParams,
    DateRangeParams
)

session_router = APIRouter(
    prefix='/session',
    tags=['sessions']
)

@session_router.get('/{session_id}', response_model= ApiResponse)
async def get_sessions(session_id : UUID
                       , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        result =  await service_manager.execute_service(
            "auth.session.read",
            session_id=session_id
        )
        if not result:
            return ApiResponse(data=result, message="Session not found")
        return ApiResponse(data=result, message="Session retrieved successfully")
    except HTTPException:
        raise 
    except Exception:
        raise

@session_router.get('/', response_model=PaginatedResponse,status_code=status.HTTP_200_OK)
async def get_sessions(
                       search_params: dict = Depends(session_search_params),
                       pagination: PaginationParams = Depends(pagination_params),
                       sorting: SortParams = Depends(sort_params),
                       date_range: DateRangeParams = Depends(date_range_params),
                       service_manager: ServiceManager = Depends(get_service_manager)
                       ):
    try:
        results = await service_manager.execute_service(
            "auth.session.search_sessions",
            search_params=search_params,
            pagination=pagination,
            sorting=sorting,
            date_range=date_range
        )
        if results:
            return PaginatedResponse(data=results
                                     , message="Sessions retrieved successfully"
                                     , pagination_info=PaginationInfo(
                                         limit=pagination.limit,
                                         offset=pagination.offset,
                                         total_count=len(results),
                                         has_next=len(results) == pagination.limit,
                                         has_previous=pagination.offset > 0
                                     ))
        else:
            raise HTTPException(status_code=404, detail="No sessions found")
    except HTTPException:
        raise
    except Exception: 
        raise HTTPException(status_code=500, detail="Internal Server Error")


@session_router.delete('/{session_id}/desactivate', status_code=status.HTTP_204_NO_CONTENT)
async def delete_session( 
                           session_id : UUID
                         ,service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service(
            "auth.session.delete",
            session_id=session_id
        )
    except HTTPException:
        raise
    except Exception:
        raise