from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from uuid import UUID
import logging
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager
from backend.schemas.card_catalog.card import BaseCard, CreateCard, CreateCards
from backend.dependancies.query_deps import (sort_params
                                             ,card_search_params
                                             ,pagination_params
                                             ,PaginationParams
                                             ,SortParams)
logger = logging.getLogger(__name__)

card_reference_router = APIRouter(
    prefix="/card-reference",
    tags=['cards'],
    responses={404:{'description' : 'Not found'}}
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
                    search: dict = Depends(card_search_params)
                        ):
    try:
        result = await service_manager.execute_service(
            "card_catalog.card.search",
             limit=pagination.limit,
            offset=pagination.offset,
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
@card_reference_router.post('/', response_model=None, status_code=status.HTTP_201_CREATED)
async def insert_card( card : CreateCard
                      , service_manager: ServiceManager = Depends(get_service_manager)
                      ):
    try:
        await service_manager.execute_service("card_catalog.card.create"
                                              , card=card)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert card: {str(e)}")

#not tested
@card_reference_router.post('/bulk', response_model=None, status_code=status.HTTP_201_CREATED)
async def insert_cards( cards : List[CreateCard]
                       , service_manager: ServiceManager = Depends(get_service_manager)):
    cards : CreateCards = CreateCards(items=cards)
    try:
        await service_manager.execute_service("card_catalog.card.create_many", cards=cards)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert cards: {str(e)}")
"""
@router.post('/from_json')
async def insert_cards_json( parsed_cards : CreateCards = Depends(services.get_parsed_cards)
                            , service_manager: ServiceManager = Depends(get_service_manager)
                            ):
        try:
            await service_manager.execute_service("card_catalog.card.create", cards=parsed_cards)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to insert cards: {str(e)}")
        

@router.post("/large_json")
async def upload_large_cards_json( file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    await services.upload_large_cards_json(file, background_tasks)
"""
    
#not tested
@card_reference_router.delete('/{card_id}')
async def delete_card(card_id : UUID, service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service("card_catalog.card.delete", card_id=card_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete card: {str(e)}")