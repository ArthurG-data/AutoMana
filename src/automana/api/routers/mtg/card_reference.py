import os
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from uuid import UUID
from automana.api.schemas.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo, ErrorResponse
from automana.core.models.card_catalog.card import BaseCard, CardDetail, CardSuggestionResponse, CreateCard, CreateCards, CatalogStats
from automana.core.models.card_catalog.price_history import PriceHistoryResponse
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.dependancies.query_deps import (
    sort_params,
    card_search_params,
    pagination_params,
    date_range_params,
    PaginationParams,
    SortParams,
    DateRangeParams,
)

logger = logging.getLogger(__name__)

BULK_INSERT_LIMIT = 50

_CARD_ERRORS = {
    422: {"description": "Validation error — malformed or missing fields"},
    500: {"description": "Internal server error", "model": ErrorResponse},
}

card_reference_router = APIRouter(
    prefix="/card-reference",
    tags=["Card Catalogue"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal Server Error"},
    },
)


@card_reference_router.get(
    '/suggest',
    summary="Autocomplete card names",
    description=(
        "Returns up to `limit` card-name suggestions matching the partial query `q` "
        "using typo-tolerant fuzzy matching (pg_trgm). Minimum query length is 2 "
        "characters. Results are cached for 10 minutes. Useful for search-as-you-type "
        "UI components."
    ),
    response_model=ApiResponse[CardSuggestionResponse],
    operation_id="cards_suggest",
    responses={
        400: {"description": "Query string too short (minimum 2 characters)"},
        **_CARD_ERRORS,
    },
)
async def suggest_cards(
    service_manager: ServiceManagerDep,
    q: str = Query(..., min_length=2, description="Partial card name to autocomplete"),
    limit: int = Query(10, ge=1, le=20, description="Maximum number of suggestions to return (1–20)"),
) -> ApiResponse[CardSuggestionResponse]:
    try:
        result = await service_manager.execute_service(
            "card_catalog.card.suggest",
            query=q,
            limit=limit,
        )
        return ApiResponse(data=result, message="Suggestions retrieved successfully")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@card_reference_router.get(
    '/stats',
    summary="Catalog statistics",
    description="Returns metadata about the card catalog including total card versions, data source, and last update time.",
    response_model=ApiResponse[CatalogStats],
    operation_id="cards_stats",
    responses={**_CARD_ERRORS},
)
async def get_catalog_stats(
    service_manager: ServiceManagerDep,
) -> ApiResponse[CatalogStats]:
    try:
        result = await service_manager.execute_service("card_catalog.card.stats")
        return ApiResponse(data=result, message="Catalog stats retrieved successfully")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@card_reference_router.get(
    '/{card_id}',
    summary="Get a card by its UUID",
    description=(
        "Returns the full card record for the given Scryfall-compatible UUID. "
        "If no card matches, an empty `data` list is returned with a descriptive "
        "message rather than a 404."
    ),
    response_model=ApiResponse[CardDetail],
    operation_id="cards_get_by_id",
    responses={
        404: {"description": "Card not found"},
        **_CARD_ERRORS,
    },
)
async def get_card(
    card_id: UUID,
    service_manager: ServiceManagerDep,
) -> ApiResponse[CardDetail]:
    try:
        result = await service_manager.execute_service(
            "card_catalog.card.get",
            card_id=card_id,
        )
        card = result.cards[0] if result.cards else None
        if not card:
            return ApiResponse(data=[], message="No card found for the given ID")
        return ApiResponse(data=card, message="Card retrieved successfully")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@card_reference_router.get(
    '/{card_id}/price-history',
    summary="Get card price history",
    description=(
        "Returns aggregated daily price history for a card. Supports time range selection "
        "via the `price_range` parameter. Prices are aggregated across all sources "
        "(MTGStocks, TCGPlayer, etc.) and are in USD. Responses are cached for 24 hours."
    ),
    response_model=ApiResponse[PriceHistoryResponse],
    operation_id="cards_price_history",
    responses={
        400: {"description": "Invalid price_range parameter"},
        404: {"description": "Card not found"},
        **_CARD_ERRORS,
    },
)
async def get_card_price_history(
    card_id: UUID,
    service_manager: ServiceManagerDep,
    price_range: str = Query('1m', regex='^(1w|1m|3m|1y|all)$', description="Time range: 1w, 1m, 3m, 1y, or all"),
    finish: Optional[str] = Query(None, regex='^(nonfoil|foil|etched|surge_foil|ripple_foil|rainbow_foil)$', description="Finish type (nonfoil, foil, etched, etc.). Omit to aggregate all finishes."),
) -> ApiResponse[PriceHistoryResponse]:
    """Get price history for a card in the specified time range."""
    try:
        # Map price_range to days_back
        range_map = {
            '1w': 7,
            '1m': 30,
            '3m': 90,
            '1y': 365,
            'all': None,
        }
        days_back = range_map[price_range]

        result = await service_manager.execute_service(
            "card_catalog.card.get_price_history",
            card_id=card_id,
            days_back=days_back,
            finish=finish,
        )

        return ApiResponse(
            data=result,
            message="Price history retrieved successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching price history", extra={"card_id": str(card_id), "error": str(e)})
        raise HTTPException(status_code=500, detail="Internal Server Error")


@card_reference_router.get(
    '/',
    summary="Search and list cards (paginated)",
    description=(
        "Returns a paginated list of MTG cards. Supports full-text and field-level "
        "filtering: `name`, `oracle_text`, `format`, `set`, `rarity`, and more. "
        "Also accepts `released_after` / `released_before` date range filters and "
        "standard `sort_by` / `sort_order` / `limit` / `offset` controls. "
        "Results are cached for 60 minutes per unique filter combination."
    ),
    response_model=PaginatedResponse[BaseCard],
    operation_id="cards_list",
    responses=_CARD_ERRORS,
)
async def list_cards(
    service_manager: ServiceManagerDep,
    pagination: PaginationParams = Depends(pagination_params),
    sorting: SortParams = Depends(sort_params),
    search: dict = Depends(card_search_params),
    date_range: DateRangeParams = Depends(date_range_params),
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
            **search,
        )
        cards = result.cards if result else []
        total_count = result.total_count if result else 0
        return PaginatedResponse[BaseCard](
            data=cards,
            pagination=PaginationInfo(
                limit=pagination.limit,
                offset=pagination.offset,
                total_count=total_count,
                has_next=len(cards) == pagination.limit,
                has_previous=pagination.offset > 0,
            ),
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@card_reference_router.post(
    '/',
    summary="Insert a single card",
    description=(
        "Inserts a new MTG card record into the catalogue. The request body must "
        "conform to the `CreateCard` schema, which maps closely to the Scryfall card "
        "object format. Returns the newly created card's UUID on success.\n\n"
        "> **Note:** This endpoint is not yet covered by integration tests."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="cards_create",
    responses={
        409: {"description": "Card with this ID already exists"},
        **_CARD_ERRORS,
    },
)
async def insert_card(
    card: CreateCard,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.card.create",
            card=card,
        )
        if not result:
            raise HTTPException(status_code=500, detail="Failed to insert card")
        return ApiResponse(data={"card_id": str(result)}, message="Card inserted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert card: {str(e)}")


@card_reference_router.post(
    '/bulk',
    summary="Bulk-insert up to 50 cards",
    description=(
        "Inserts up to **50** MTG card records in a single request. Returns a summary "
        "of successful and failed inserts along with the success rate. "
        "For larger batches use `POST /card-reference/upload-file`.\n\n"
        "> **Note:** This endpoint is not yet covered by integration tests."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="cards_bulk_create",
    responses={
        400: {"description": f"Payload exceeds the {BULK_INSERT_LIMIT}-card limit or is empty"},
        **_CARD_ERRORS,
    },
)
async def bulk_insert_cards(
    cards: List[CreateCard],
    service_manager: ServiceManagerDep,
):
    validated_cards: CreateCards = CreateCards(items=cards)
    try:
        if len(cards) > BULK_INSERT_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Bulk insert limited to {BULK_INSERT_LIMIT} cards. "
                    f"You provided {len(cards)} cards. "
                    "Use the file upload endpoint for larger batches."
                ),
            )
        if len(cards) == 0:
            raise HTTPException(
                status_code=400,
                detail="No cards provided for bulk insert",
            )
        result = await service_manager.execute_service(
            "card_catalog.card.create_many",
            cards=validated_cards,
        )
        if not result:
            raise HTTPException(status_code=500, detail="Failed to insert cards")
        return ApiResponse(
            data={
                "InsertedCards": result.successful_inserts,
                "NotInsertedCards": result.failed_inserts,
                "PercentageSuccess": result.success_rate,
            },
            message="Bulk insert completed",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert cards: {str(e)}")


@card_reference_router.delete(
    '/{card_id}',
    summary="Delete a card by its UUID",
    description=(
        "Permanently removes the card record identified by `card_id` from the "
        "catalogue. Returns the deleted card's UUID in the response body.\n\n"
        "> **Note:** This endpoint is not yet covered by integration tests."
    ),
    response_model=ApiResponse,
    operation_id="cards_delete",
    responses={
        404: {"description": "Card not found"},
        **_CARD_ERRORS,
    },
)
async def delete_card(
    card_id: UUID,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service("card_catalog.card.delete", card_id=card_id)
        return ApiResponse(data={"card_id": str(card_id)}, message="Card deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete card: {str(e)}")


@card_reference_router.post(
    "/test-service",
    summary="[Dev] Test the large-JSON processing service",
    description=(
        "**Development/diagnostic endpoint.** Invokes the "
        "`card_catalog.card.process_large_json` service with a server-side file path "
        "and returns the raw result. The file must already exist on the server "
        "filesystem. **Do not expose in production.**"
    ),
    response_model=ApiResponse,
    operation_id="cards_test_service",
    responses={
        400: {"description": "File not found at the provided path"},
        **_CARD_ERRORS,
    },
)
async def test_service(
    file_path: str,
    service_manager: ServiceManagerDep,
):
    try:
        if not os.path.exists(file_path):
            raise HTTPException(status_code=400, detail=f"File not found: {file_path}")
        result = await service_manager.execute_service(
            "card_catalog.card.process_large_json",
            file_path=file_path,
        )
        return ApiResponse(
            data={"raw_result": str(result)},
            message="Service test completed",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service test failed: {str(e)}")
