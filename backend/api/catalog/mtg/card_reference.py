import os,tempfile, logging
from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, BackgroundTasks
from uuid import UUID
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.schemas.card_catalog.card import BaseCard, CreateCard, CreateCards
from backend.dependancies.service_deps import ServiceManagerDep
from backend.dependancies.query_deps import (sort_params
                                             ,card_search_params
                                             ,pagination_params
                                             , date_range_params
                                             ,PaginationParams
                                             ,SortParams
                                             , DateRangeParams)

BULK_INSERT_LIMIT = 50

card_reference_router = APIRouter(
    prefix="/card-reference",
    tags=['cards'],
    responses={404:{'description' : 'Not found'},
               500: {'description': 'Internal Server Error'},
               }
)

@card_reference_router.get('/{card_id}', response_model=ApiResponse[BaseCard])
async def get_card_info(card_id: UUID
                        , service_manager: ServiceManagerDep
                        ) -> ApiResponse[BaseCard]:
    try:
        result =await service_manager.execute_service(
            "card_catalog.card.get",
            card_id=card_id
        )
        #get the card
        card = result.cards[0] if result.cards else None
        
        if not card:
            return ApiResponse(data=[], message="No Card to retrieve")
        return ApiResponse(data=card, message="Card retrieved successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@card_reference_router.get('/', response_model=PaginatedResponse[BaseCard])
async def get_cards(
                    service_manager: ServiceManagerDep,
                    pagination: PaginationParams = Depends(pagination_params),
                    sorting: SortParams = Depends(sort_params),
                    search: dict = Depends(card_search_params),
                    date_range: DateRangeParams = Depends(date_range_params)
                        ):
    try:
        result = await service_manager.execute_service(
            "card_catalog.card.search",
             limit=pagination.limit,
            offset=pagination.offset,
            released_after=date_range.created_after,
            released_before=date_range.created_before,
            sort_by=sorting.sort_by,
            sort_order=sorting.sort_order,
            **search)
        cards = result.cards if result else []

        total_count = result.total_count if result else 0
        if cards:
            return PaginatedResponse[BaseCard](
                data=cards,
                pagination=PaginationInfo(
                    limit=pagination.limit,
                    offset=pagination.offset,
                    total_count=total_count,
                    has_next=len(cards) == pagination.limit,
                    has_previous=pagination.offset > 0
                )
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")

#not tested
@card_reference_router.post('/', status_code=status.HTTP_201_CREATED)
async def insert_card( card : CreateCard
                      , service_manager: ServiceManagerDep
                      ):
    try:
        result =await service_manager.execute_service("card_catalog.card.create"
                                              , card=card)
        

        if not result:
            raise HTTPException(status_code=500, detail="Failed to insert card")
        return ApiResponse(data={"card_id": str(result)}, message="Card inserted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert card: {str(e)}")

#not tested
@card_reference_router.post('/bulk', response_model=None,)
async def insert_cards( cards : List[CreateCard]
                       , service_manager: ServiceManagerDep
                       ):
    validated_cards : CreateCards = CreateCards(items=cards)
    try:
        if len(cards) > BULK_INSERT_LIMIT:
            raise HTTPException(
                status_code=400, 
                detail=f"Bulk insert limited to {BULK_INSERT_LIMIT} cards. "
                       f"You provided {len(cards)} cards. "
                       f"Use the file upload endpoint for larger batches."
            )
        if len(cards) == 0:
            raise HTTPException(
                status_code=400,
                detail="No cards provided for bulk insert"
            )
        
        result = await service_manager.execute_service("card_catalog.card.create_many", cards=validated_cards)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to insert cards")
        return ApiResponse(data = {"InsertedCards": result.successful_inserts,
                                   "NotInsertedCards": result.failed_inserts,
                                   "PercentageSuccess": result.success_rate}
                                   , message="Bulk insert completed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert cards: {str(e)}")

#not tested
@card_reference_router.delete('/{card_id}')
async def delete_card(card_id : UUID
                      , service_manager: ServiceManagerDep):
    try:
        await service_manager.execute_service("card_catalog.card.delete", card_id=card_id)
        return ApiResponse(data={"card_id": str(card_id)}, message="Card deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete card: {str(e)}")
    
@card_reference_router.post("/test-service", response_model=ApiResponse)
async def test_service_only(
    file_path: str,
    service_manager: ServiceManagerDep
):
    """
    Simple test of the service with minimal parameters
    """
    try:
        if not os.path.exists(file_path):
            raise HTTPException(status_code=400, detail=f"File not found: {file_path}")
        
        
        # Call service with minimal parameters
        result = await service_manager.execute_service(
            "card_catalog.card.process_large_json",
            file_path=file_path
        )
        
        return ApiResponse(
            data={"raw_result": str(result)},
            message="Service test completed"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service test failed: {str(e)}")