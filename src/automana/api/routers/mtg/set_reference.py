import logging
from fastapi import APIRouter, Query, Depends, HTTPException, Response, status
from typing import List, Optional
from uuid import UUID

from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import (
    ApiResponse,
    PaginatedResponse,
    ErrorResponse,
    PaginationInfo,
)
from automana.core.models.card_catalog.set import NewSet, NewSets, UpdatedSet

logger = logging.getLogger(__name__)

_SET_ERRORS = {
    422: {"description": "Validation error — malformed or missing fields"},
    500: {"description": "Internal server error", "model": ErrorResponse},
}

router = APIRouter(
    prefix="/set-reference",
    tags=["Card Catalogue"],
    responses={
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)


@router.get(
    '/{set_id}',
    summary="Get a set by its UUID",
    description=(
        "Returns the full details of the MTG set identified by `set_id`. "
        "Raises 404 if the set does not exist."
    ),
    response_model=ApiResponse,
    operation_id="sets_get_by_id",
    responses={
        404: {"description": "Set not found"},
        **_SET_ERRORS,
    },
)
async def get_set(
    set_id: UUID,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.set.get",
            set_id=set_id,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Set not found")
        return ApiResponse(
            success=True,
            data=result,
            message="Set retrieved successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    '/',
    summary="List sets (paginated)",
    description=(
        "Returns a paginated list of MTG sets. Optionally accepts a list of "
        "`ids` (set code strings) to filter results to specific sets. "
        "Supports `limit` (max 100) and `offset` for pagination."
    ),
    response_model=PaginatedResponse,
    operation_id="sets_list",
    responses=_SET_ERRORS,
)
async def list_sets(
    service_manager: ServiceManagerDep,
    limit: int = Query(default=100, le=100, ge=1, description="Maximum number of sets to return (1–100)"),
    offset: int = Query(default=0, ge=0, description="Number of sets to skip"),
    ids: Optional[List[str]] = Query(default=None, description="Optional list of set codes to filter by"),
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.set.get_all",
            limit=limit,
            offset=offset,
            ids=ids,
        )
        return PaginatedResponse(
            success=True,
            data=result,
            message="Sets retrieved successfully",
            pagination=PaginationInfo(
                limit=limit,
                offset=offset,
                total_count=len(result),
                has_next=len(result) > limit,
                has_previous=offset > 0,
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    '/',
    summary="Insert a new set",
    description=(
        "Adds a new MTG set to the reference catalogue. The set must not already "
        "exist (unique set code). Returns 201 Created on success."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="sets_create",
    responses={
        409: {"description": "Set with this code already exists"},
        **_SET_ERRORS,
    },
)
async def insert_set(
    new_set: NewSet,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "card_catalog.set.add",
            new_set=new_set,
        )
    except HTTPException:
        raise
    except Exception:
        raise


@router.post(
    '/bulk',
    summary="Bulk-insert multiple sets",
    description=(
        "Inserts multiple MTG sets into the reference catalogue in a single request. "
        "Useful for seeding the database from external data sources. "
        "Returns 201 Created on success."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="sets_bulk_create",
    responses={
        400: {"description": "Empty sets list provided"},
        **_SET_ERRORS,
    },
)
async def bulk_insert_sets(
    sets: NewSets,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "card_catalog.set.create_bulk",
            sets=sets,
        )
    except HTTPException:
        raise
    except Exception:
        raise


@router.put(
    '/{set_id}',
    summary="Update a set",
    description=(
        "Updates the fields of the MTG set identified by `set_id`. "
        "Partial updates are supported — only provided fields are changed. "
        "Returns 204 No Content on success."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="sets_update",
    responses={
        404: {"description": "Set not found"},
        **_SET_ERRORS,
    },
)
async def update_set(
    set_id: UUID,
    update_set: UpdatedSet,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "card_catalog.set.update",
            set_id=set_id,
            update_set=update_set,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception:
        raise


@router.delete(
    '/{set_id}',
    summary="Delete a set by its UUID",
    description=(
        "Permanently removes the MTG set identified by `set_id` from the "
        "reference catalogue. Returns 204 No Content on success."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="sets_delete",
    responses={
        404: {"description": "Set not found"},
        **_SET_ERRORS,
    },
)
async def delete_set(
    set_id: UUID,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "card_catalog.set.delete",
            set_id=set_id,
        )
    except HTTPException:
        raise
    except Exception:
        raise
