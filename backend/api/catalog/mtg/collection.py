from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
from uuid import UUID
from backend.schemas.collections.collection import CreateCollection, UpdateCollection, PublicCollection, PublicCollectionEntry, UpdateCollectionEntry, NewCollectionEntry
from backend.dependancies.service_deps import ServiceManagerDep
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, ErrorResponse, PaginationInfo
from backend.dependancies.auth.users import CurrentUserDep

router = APIRouter(
     prefix='/collection',
    tags=['collection'],
    responses={401: {'description': 'Unauthorized', 'model': ErrorResponse},
        403: {'description': 'Forbidden', 'model': ErrorResponse},
        404: {'description': 'Not found', 'model': ErrorResponse},
        500: {'description': 'Internal server error', 'model': ErrorResponse}
        }
)

@router.post('/', response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def add_collection(
    created_collection: CreateCollection, 
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep
) -> ApiResponse:
    result = await service_manager.execute_service(
        "card_catalog.collection.add"
        ,created_collection= created_collection
        ,user=current_user
        )
    return ApiResponse(data=result)

@router.delete('/{collection_id}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_collection(
    collection_id: UUID, 
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep
):
    result = await service_manager.execute_service(
        "card_catalog.collection.delete"
        , user=current_user
        ,collection_id= collection_id)
    if result is not True:
        return ApiResponse(status=404, message="Collection not found")


@router.get('/{collection_id}', response_model=ApiResponse, status_code=status.HTTP_200_OK)
async def get_collection(
    collection_id: UUID, 
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep
):
    result = await service_manager.execute_service(
        "card_catalog.collection.get"
        , collection_id =collection_id
        , user = current_user)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return ApiResponse(data=result)

@router.get('/', response_model=List[PublicCollection])
async def get_collection(
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    collection_ids: Optional[List[UUID]] = Query(None, description="Specific collection IDs to retrieve"),
    limit: int = Query(100, le=100, description="Maximum number of collections"),
    offset: int = Query(0, ge=0, description="Number of collections to skip")
):
    try:
        # Determine which service method to call based on parameters
        if collection_ids:
            # Get specific collections by IDs
            result = await service_manager.execute_service(
                "card_catalog.collection.get_many",
                user_id=UUID(current_user.unique_id),
                collection_ids=collection_ids
            )
            # Format as paginated response for consistency
            return PaginatedResponse(
                success=True,
                data=result,
                pagination=PaginationInfo(
                    limit=len(result),
                    offset=0,
                    total_count=len(result),
                    has_next=False,
                    has_previous=False
                ),
                message=f"Retrieved {len(result)} specific collections"
            )
        else:
            # Get all collections with optional name filter
            result = await service_manager.execute_service(
                "card_catalog.collection.get_all",
                user_id=UUID(current_user.unique_id),
                limit=limit,
                offset=offset,
            )
            
            collections = result.get("collections", [])
            total_count = result.get("total_count", 0)
            
            return PaginatedResponse(
                success=True,
                data=collections,
                pagination=PaginationInfo(
                    limit=limit,
                    offset=offset,
                    total_count=total_count,
                    has_next=offset + limit < total_count,
                    has_previous=offset > 0
                ),
                message="Collections retrieved successfully"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.put('/{collection_id}', status_code=204)
async def change_collection(
    collection_id: str, 
    updated_collection: UpdateCollection, 
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep
):
    return await service_manager.execute_service(
        "card_catalog.collection.update",  collection_id=collection_id, updated_collection=updated_collection, user=current_user)

#########################to complete#######################
@router.delete('{collection_id}/{entry_id}')
async def delete_entry(
    collection_id: str, 
    entry_id: UUID,
    service_manager: ServiceManagerDep
):
    return await service_manager.execute_service(
        "card_catalog.collection.delete_entry", collection_id, entry_id)
    
@router.get('{collection_id}/{entry_id}', response_model=PublicCollectionEntry)
async def get_entry(
    collection_id: str, 
    entry_id: UUID,
    service_manager: ServiceManagerDep
):
    return await service_manager.execute_service(
        "card_catalog.collection.get_entry", collection_id, entry_id)
    
    query = """ SELECT c.item_id, c.collection_id,  c.unique_card_id, c.is_foil, c.purchase_date,c.purchase_price, rc.condition_description AS condition
                FROM collectionItems c
                JOIN Ref_Condition rc ON rc.condition_code = c.condition
                WHERE item_id = %s
            """
    try:
        return  execute_select_query(conn, query, (entry_id,), select_all=False)
    except Exception:
            raise 

