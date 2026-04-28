from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
from uuid import UUID
from automana.core.exceptions.service_layer_exceptions.card_catalogue.card_catalog_exceptions import (
    CollectionNotFoundError,
    CollectionAccessDeniedError,
)
from automana.core.models.collections.collection import (
    CreateCollection,
    UpdateCollection,
    PublicCollection,
    PublicCollectionEntry,
    UpdateCollectionEntry,
    AddCollectionEntryRequest,
)
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import (
    ApiResponse,
    PaginatedResponse,
    ErrorResponse,
    PaginationInfo,
)
from automana.api.dependancies.auth.users import CurrentUserDep, get_current_active_user

_COLLECTION_ERRORS = {
    401: {"description": "Not authenticated — valid session_id cookie required", "model": ErrorResponse},
    403: {"description": "Forbidden — collection belongs to a different user", "model": ErrorResponse},
    422: {"description": "Validation error — malformed or missing fields"},
    500: {"description": "Internal server error", "model": ErrorResponse},
}

router = APIRouter(
    prefix='/collection',
    tags=["Collections"],
    dependencies=[Depends(get_current_active_user)],
    responses={
        401: {"description": "Unauthorized", "model": ErrorResponse},
        403: {"description": "Forbidden", "model": ErrorResponse},
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)


@router.post(
    '/',
    summary="Create a new collection",
    description=(
        "Creates a new MTG card collection owned by the currently authenticated user. "
        "The collection name must be unique per user and is limited to 20 characters. "
        "Returns the newly created collection data."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="collections_create",
    responses={
        409: {"description": "A collection with this name already exists for this user"},
        **_COLLECTION_ERRORS,
    },
)
async def create_collection(
    created_collection: CreateCollection,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
) -> ApiResponse:
    result = await service_manager.execute_service(
        "card_catalog.collection.add",
        created_collection=created_collection,
        user=current_user,
    )
    return ApiResponse(data=result)


@router.get(
    '/{collection_id}',
    summary="Get a collection by ID",
    description=(
        "Returns the full details of the collection identified by `collection_id`. "
        "The collection must belong to the currently authenticated user."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    operation_id="collections_get_by_id",
    responses={
        404: {"description": "Collection not found or does not belong to this user"},
        **_COLLECTION_ERRORS,
    },
)
async def get_collection(
    collection_id: UUID,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.collection.get",
            collection_id=collection_id,
            user=current_user,
        )
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except CollectionAccessDeniedError:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ApiResponse(data=result)


@router.get(
    '/',
    summary="List collections for the current user",
    description=(
        "Returns a paginated list of all collections owned by the authenticated user. "
        "Optionally accepts a `collection_ids` query parameter to retrieve specific "
        "collections by UUID. Supports `limit` and `offset` for pagination."
    ),
    response_model=PaginatedResponse,
    operation_id="collections_list",
    responses=_COLLECTION_ERRORS,
)
async def list_collections(
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    collection_ids: Optional[List[UUID]] = Query(
        None, description="Specific collection UUIDs to retrieve"
    ),
    limit: int = Query(100, le=100, description="Maximum number of collections to return"),
    offset: int = Query(0, ge=0, description="Number of collections to skip"),
):
    try:
        if collection_ids:
            result = await service_manager.execute_service(
                "card_catalog.collection.get_many",
                user_id=current_user.unique_id,
                collection_id=collection_ids,
            )
            return PaginatedResponse(
                success=True,
                data=result,
                pagination=PaginationInfo(
                    limit=len(result),
                    offset=0,
                    total_count=len(result),
                    has_next=False,
                    has_previous=False,
                ),
                message=f"Retrieved {len(result)} specific collections",
            )
        else:
            result = await service_manager.execute_service(
                "card_catalog.collection.get_all",
                user_id=current_user.unique_id,
            )
            return PaginatedResponse(
                success=True,
                data=result,
                pagination=PaginationInfo(
                    limit=limit,
                    offset=offset,
                    total_count=len(result),
                    has_next=False,
                    has_previous=offset > 0,
                ),
                message="Collections retrieved successfully",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    '/{collection_id}',
    summary="Update a collection",
    description=(
        "Updates the `collection_name`, `description`, and/or `is_active` flag of "
        "the specified collection. The collection must belong to the authenticated "
        "user. Partial updates are supported — only provided fields are changed. "
        "Returns 204 No Content on success."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="collections_update",
    responses={
        404: {"description": "Collection not found or does not belong to this user"},
        **_COLLECTION_ERRORS,
    },
)
async def update_collection(
    collection_id: UUID,
    updated_collection: UpdateCollection,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    return await service_manager.execute_service(
        "card_catalog.collection.update",
        collection_id=collection_id,
        updated_collection=updated_collection,
        user=current_user,
    )


@router.delete(
    '/{collection_id}',
    summary="Delete a collection",
    description=(
        "Permanently deletes the collection identified by `collection_id`. "
        "The collection must belong to the currently authenticated user. "
        "Returns 204 No Content on success."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="collections_delete",
    responses={
        404: {"description": "Collection not found or does not belong to this user"},
        **_COLLECTION_ERRORS,
    },
)
async def delete_collection(
    collection_id: UUID,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "card_catalog.collection.delete",
            user=current_user,
            collection_id=collection_id,
        )
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")


@router.post(
    '/{collection_id}/entries',
    summary="Add a card to a collection",
    description=(
        "Adds a card version to the specified collection. The card can be identified by "
        "`card_version_id` (from `/suggest`), by `scryfall_id`, or by `set_code` + "
        "`collector_number`. Returns the created entry with resolved card details."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="collection_entries_add",
    responses={
        404: {"description": "Collection or card not found"},
        **_COLLECTION_ERRORS,
    },
)
async def add_entry(
    collection_id: UUID,
    request: AddCollectionEntryRequest,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.collection.add_entry",
            collection_id=collection_id,
            user=current_user,
            request=request,
        )
        return ApiResponse(data=result)
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")


@router.get(
    '/{collection_id}/entries',
    summary="List all entries in a collection",
    description="Returns all cards in the specified collection owned by the authenticated user.",
    response_model=ApiResponse,
    operation_id="collection_entries_list",
    responses={
        404: {"description": "Collection not found"},
        **_COLLECTION_ERRORS,
    },
)
async def list_entries(
    collection_id: UUID,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.collection.list_entries",
            collection_id=collection_id,
            user=current_user,
        )
        return ApiResponse(data=result)
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")


@router.get(
    '/{collection_id}/entries/{entry_id}',
    summary="Get a single collection entry",
    response_model=ApiResponse,
    operation_id="collection_entries_get",
    responses={
        404: {"description": "Entry not found"},
        **_COLLECTION_ERRORS,
    },
)
async def get_entry(
    collection_id: UUID,
    entry_id: UUID,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.collection.get_entry",
            collection_id=collection_id,
            entry_id=entry_id,
            user=current_user,
        )
        return ApiResponse(data=result)
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Entry not found")


@router.delete(
    '/{collection_id}/entries/{entry_id}',
    summary="Remove a card from a collection",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="collection_entries_delete",
    responses={
        404: {"description": "Entry not found"},
        **_COLLECTION_ERRORS,
    },
)
async def delete_entry(
    collection_id: UUID,
    entry_id: UUID,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "card_catalog.collection.delete_entry",
            collection_id=collection_id,
            entry_id=entry_id,
            user=current_user,
        )
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Entry not found")
