import os
import tempfile
from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, BackgroundTasks
from uuid import UUID
import logging
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager
from backend.schemas.card_catalog.card import BaseCard, CreateCard, CreateCards
from backend.dependancies.query_deps import (sort_params
                                             ,card_search_params
                                             ,pagination_params
                                             , date_range_params
                                             ,PaginationParams
                                             ,SortParams
                                             , DateRangeParams)
logger = logging.getLogger(__name__)

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
                        , service_manager: ServiceManager = Depends(get_service_manager)
                        ) -> ApiResponse[BaseCard]:
    try:
        result =await service_manager.execute_service(
            "card_catalog.card.search",
            card_id=card_id
        )
        if not result:
            return ApiResponse(result, message="No Card to retrieve")
        return ApiResponse(result, message="Card retrieved successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching cards: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@card_reference_router.get('/', response_model=PaginatedResponse[BaseCard])
async def get_cards(
                    service_manager: ServiceManager = Depends(get_service_manager),
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
        cards = result.get("cards", []) if isinstance(result, dict) else []
        total_count = result.get("total_count", 0) if isinstance(result, dict) else 0
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
        logger.error(f"Error searching users: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

#not tested
@card_reference_router.post('/', status_code=status.HTTP_201_CREATED)
async def insert_card( card : CreateCard
                      , service_manager: ServiceManager = Depends(get_service_manager)
                      ):
    try:
        result =await service_manager.execute_service("card_catalog.card.create"
                                              , card=card)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to insert card")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert card: {str(e)}")

#not tested
@card_reference_router.post('/bulk', response_model=None,)
async def insert_cards( cards : List[CreateCard]
                       , service_manager: ServiceManager = Depends(get_service_manager)):
    validated_cards : CreateCards = CreateCards(items=cards)
    return validated_cards.prepare_for_db()
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
        
        logger.info(f"Processing bulk insert of {len(cards)} cards")

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


@card_reference_router.post("/upload-file")
async def upload_large_cards_json( 
                                file: UploadFile = File(...)
                                  ,service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        # Validate file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=400,
                detail="Only JSON files are supported"
            )
        
        # Check file size (optional limit)
        max_size =  1024 * 1024 * 1024  # 1GB default

        logger.info(f"Processing file upload: {file.filename}")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
            content = await file.read()
            
            if len(content) > max_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large. Maximum size: {max_size / 1024 / 1024:.1f}MB"
                )
            
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Process file using enhanced service
        try:
            result = await service_manager.execute_service(
                "card_catalog.card.process_large_json",
                file_path=temp_file_path,
            )
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Convert result to dict if it's a stats object
            if hasattr(result, 'to_dict'):
                result_data = result.to_dict()
            else:
                result_data = result
            
            return ApiResponse(
                data={
                    "filename": file.filename,
                    "file_size_mb": round(len(content) / 1024 / 1024, 2),
                    "processing_stats": result_data
                },
                message=f"File '{file.filename}' processed successfully"
            )
            
        except Exception as processing_error:
            # Clean up temp file on error
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise processing_error
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process file upload '{file.filename}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

#not tested
@card_reference_router.delete('/{card_id}')
async def delete_card(card_id : UUID
                      , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service("card_catalog.card.delete", card_id=card_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete card: {str(e)}")
    
@card_reference_router.post("/test-service", response_model=ApiResponse)
async def test_service_only(
    file_path: str,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    """
    Simple test of the service with minimal parameters
    """
    try:
        if not os.path.exists(file_path):
            raise HTTPException(status_code=400, detail=f"File not found: {file_path}")
        
        logger.info(f"🧪 Testing service with: {file_path}")
        
        # Call service with minimal parameters
        result = await service_manager.execute_service(
            "card_catalog.card.process_large_json",
            file_path=file_path
        )
        
        return ApiResponse(
            data={"raw_result": str(result)},
            message="Service test completed"
        )
        
    except Exception as e:
        logger.error(f"❌ Service test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Service test failed: {str(e)}")