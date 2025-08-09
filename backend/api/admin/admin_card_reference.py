from fastapi import APIRouter, Depends, status
from backend.schemas.card_catalog.card import CreateCard
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager
from uuid import UUID

router = APIRouter(
    prefix='/card-reference',
    tags=['admin-cards'],
    #dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)

@router.post('/', response_model=None, status_code=status.HTTP_201_CREATED)
async def insert_card(card: CreateCard, service_manager: ServiceManager = Depends(get_service_manager)):
    return await service_manager.execute_service(
        "card_catalog.card.create",
        card=card
    )
 
@router.delete('/{card_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: UUID, service_manager: ServiceManager = Depends(get_service_manager)):
    return await service_manager.execute_service(
        "card_catalog.card.delete",
        card_id=card_id
    )