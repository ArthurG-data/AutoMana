from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo, ErrorResponse

from automana.api.dependancies.query_deps import (
    session_search_params,
    pagination_params,
    sort_params,
    date_range_params,
    PaginationParams,
    SortParams,
    DateRangeParams,
)

session_router = APIRouter(
    prefix='/session',
    tags=['Sessions'],
)

_SESSION_ERRORS = {
    401: {"description": "Not authenticated", "model": ErrorResponse},
    403: {"description": "Insufficient permissions", "model": ErrorResponse},
    500: {"description": "Internal server error", "model": ErrorResponse},
}


@session_router.get(
    '/{session_id}',
    summary="Retrieve a session by ID",
    description=(
        "Returns metadata for a single session identified by its UUID. "
        "If the session does not exist, an empty `data` field is returned "
        "with a descriptive message rather than a 404."
    ),
    response_model=ApiResponse,
    operation_id="sessions_get_by_id",
    responses={
        404: {"description": "Session not found"},
        **_SESSION_ERRORS,
    },
)
async def get_session(
    session_id: UUID,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "auth.session.read",
            session_id=session_id,
        )
        if not result:
            return ApiResponse(data=result, message="Session not found")
        return ApiResponse(data=result, message="Session retrieved successfully")
    except HTTPException:
        raise
    except Exception:
        raise


@session_router.get(
    '/',
    summary="Search and list sessions (paginated)",
    description=(
        "Returns a paginated list of sessions filtered by the provided query "
        "parameters. Supports searching by user, status, date range, and common "
        "sort/pagination controls. Returns 404 when no sessions match the filter."
    ),
    response_model=PaginatedResponse,
    status_code=status.HTTP_200_OK,
    operation_id="sessions_list",
    responses={
        404: {"description": "No sessions match the provided filters"},
        **_SESSION_ERRORS,
    },
)
async def list_sessions(
    service_manager: ServiceManagerDep,
    search_params: dict = Depends(session_search_params),
    pagination: PaginationParams = Depends(pagination_params),
    sorting: SortParams = Depends(sort_params),
    date_range: DateRangeParams = Depends(date_range_params),
):
    try:
        results = await service_manager.execute_service(
            "auth.session.search_sessions",
            search_params=search_params,
            pagination=pagination,
            sorting=sorting,
            date_range=date_range,
        )
        if results:
            return PaginatedResponse(
                data=results,
                message="Sessions retrieved successfully",
                pagination_info=PaginationInfo(
                    limit=pagination.limit,
                    offset=pagination.offset,
                    total_count=len(results),
                    has_next=len(results) == pagination.limit,
                    has_previous=pagination.offset > 0,
                ),
            )
        else:
            raise HTTPException(status_code=404, detail="No sessions found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@session_router.delete(
    '/{session_id}/deactivate',
    summary="Deactivate a session",
    description=(
        "Marks the specified session as inactive, effectively invalidating it. "
        "This is distinct from logout — the session record is retained for audit "
        "purposes. Returns 204 No Content on success."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="sessions_deactivate",
    responses={
        404: {"description": "Session not found"},
        **_SESSION_ERRORS,
    },
)
async def deactivate_session(
    session_id: UUID,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "auth.session.delete",
            session_id=session_id,
        )
    except HTTPException:
        raise
    except Exception:
        raise
