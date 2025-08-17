from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager
from backend.schemas.card_catalog.card import BaseCard

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
            raise HTTPException(status_code=404, detail="Card not found")
        return ApiResponse.success(result, message="Card retrieved successfully")
    except HTTPException:
        raise
    except Exception as e:
        return ApiResponse.error(f"Failed to retrieve card info: {str(e)}")

@card_reference_router.get('/', response_model=PaginatedResponse[BaseCard])
async def get_cards(limit: int=100
                        ,offset: int=0
                        ,service_manager: ServiceManager = Depends(get_service_manager)
                        ):
    try:
        result = await service_manager.execute_service(
            "card_catalog.card.search_many",
            limit=limit,
            offset=offset
        )
        if result:
            return PaginatedResponse[BaseCard](
                data=result,
                pagination=PaginationInfo(
                    limit=limit,
                    offset=offset,
                    total_count=len(result),
                    has_next=len(result) == limit,
                    has_previous=offset > 0
                )
            )
    except HTTPException:
        raise
    except Exception as e:
        return ApiResponse.error(f"Failed to retrieve cards: {str(e)}")
