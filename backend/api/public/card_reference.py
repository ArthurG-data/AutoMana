from fastapi import APIRouter, Depends
from uuid import UUID
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager
from backend.schemas.card_catalog.card import BaseCard

card_reference_router = APIRouter(
    prefix="/card-reference",
    tags=['cards'],
    responses={404:{'description' : 'Not found'}}
)

@card_reference_router.get('/{card_id}', response_model=ApiResponse[BaseCard])
async def get_card_info(card_id: UUID, service_manager: ServiceManager = Depends(get_service_manager)):
    return await service_manager.execute_service(
        "card_catalog.card.get",
        card_id=card_id
    )

@card_reference_router.get('/', response_model=PaginatedResponse[BaseCard])
async def get_all_cards(limit: int=100, offset: int=0, service_manager: ServiceManager = Depends(get_service_manager)):
    return await service_manager.execute_service(
        "card_catalog.card.list",
        limit=limit,
        offset=offset
    )
