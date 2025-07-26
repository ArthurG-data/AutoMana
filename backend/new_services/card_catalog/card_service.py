
from psycopg2.extras import  Json
from uuid import UUID
from fastapi import Query
from backend.repositories.card_catalog import card_queries as queries 
from backend.schemas.card_catalog import card as card_schemas
from backend.utils_new.card_catalog import data_transformer as utils
from backend.repositories.card_catalog.card_repository import CardReferenceRepository
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from typing import Annotated, Sequence, Optional
from backend.schemas.card_catalog.card import BaseCard

async def add(repository : CardReferenceRepository, value : card_schemas.CreateCard):
    values =  (
            value.card_name,
            value.cmc,
            value.mana_cost,
            value.reserved,
            value.oracle_text,
            value.set_name,
            str(value.collector_number),
            value.rarity_name,
            value.border_color,
            value.frame,
            value.layout,
            value.is_promo,
            value.is_digital,
            Json(value.card_color_identity),        # p_colors
            value.artist,
            value.artist_ids[0] if value.artist_ids else UUID("00000000-0000-0000-0000-000000000000"),
            Json(value.legalities),
            value.illustration_id,
            Json(value.types),
            Json(value.supertypes),
            Json(value.subtypes),
            Json(value.games),
            value.oversized,
            value.booster,
            value.full_art,
            value.textless,
            str(value.power) if value.power is not None else None,
            str(value.toughness) if value.toughness is not None else None,
            Json(value.promo_types),
            value.variation,
            utils.to_json_safe([f.model_dump() for f in value.card_faces]) if value.card_faces else Json([])
        )
    
    await repository.add(values)
    return {"status": "success"}

async def add_many(repository : CardReferenceRepository, values_list : card_schemas.CreateCards):
    output_list = []
    for card in values_list.items:
        values = (
            card.card_name,
            card.cmc,
            card.mana_cost,
            card.reserved,
            card.oracle_text,
            card.set_name,
            str(card.collector_number),
            card.rarity_name,
            card.border_color,
            card.frame,
            card.layout,
            card.is_promo,
            card.is_digital,
            Json(card.card_color_identity),        # p_colors
            card.artist,
            card.artist_ids[0] if card.artist_ids else UUID("00000000-0000-0000-0000-000000000000"),
            Json(card.legalities),
            card.illustration_id,
            Json(card.types),
            Json(card.supertypes),
            Json(card.subtypes),
            Json(card.games),
            card.oversized,
            card.booster,
            card.full_art,
            card.textless,
            str(card.power) if card.power is not None else None,
            str(card.toughness) if card.toughness is not None else None,
            Json(card.promo_types),
            card.variation,
            utils.to_json_safe([f.model_dump() for f in card.card_faces]) if card.card_faces else Json([])
        )
        output_list.append(values)

    await repository.add_many(output_list)
    return {"status": "success", "count": len(output_list)}

async def delete(repository : CardReferenceRepository, card_id: UUID):
    await repository.delete(card_id)
    return {"status": "success", "card_id": str(card_id)}


async def list(repository: CardReferenceRepository,
                ids: Optional[Sequence[UUID]] = None,
                limit: Annotated[int, Query(le=100)] = 100,
                offset: int = 0)-> ApiResponse:
    results = await repository.list(ids, limit=limit, offset=offset)
    cards = [BaseCard.model_validate(result) for result in results]
    return PaginatedResponse[BaseCard](
    data=cards,  # List of cards
    pagination=PaginationInfo(
        count=len(results),
        page=offset // limit + 1,
        pages=(len(results) + limit - 1) // limit,
        limit=limit
    )
)

async def get(repository: CardReferenceRepository,
               card_id: UUID,
                     ) -> ApiResponse:
    results = await repository.get(
        card_id=card_id,
    )
    
    if not results:
        return ApiResponse(status="error", message=f"Card with ID {card_id} not found")
    return ApiResponse(data=BaseCard.model_validate(results[0]))
