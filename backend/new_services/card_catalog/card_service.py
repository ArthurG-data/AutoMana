
from psycopg2.extras import  Json
from uuid import UUID
from fastapi import Query
from backend.repositories.card_catalog import card_queries as queries 
from backend.schemas.card_catalog import card as card_schemas
from backend.utils_new.card_catalog import data_transformer as utils
from backend.repositories.card_catalog.card_repository import CardReferenceRepository
from typing import Annotated, Sequence, Optional, List
from backend.schemas.card_catalog.card import BaseCard
from backend.exceptions.card_catalogue import card_exception

async def add(repository : CardReferenceRepository
              , value : card_schemas.CreateCard)-> BaseCard:
    values =  value.prepare_for_db()
    """(
            value.name,
            value.cmc,
            value.mana_cost,
            value.reserved,
            value.oracle_text,
            value.set_name,
            str(value.collector_number),
            value.rarity,
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
        )"""
    try:
        card = await repository.add(values)
        return card_schemas.BaseCard.model_validate(card)
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert card: {str(e)}")

async def add_many(repository : CardReferenceRepository, values_list : card_schemas.CreateCards):
    cards = values_list.prepare_for_db()
    """
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
    """
    try:
        result = await repository.add_many(cards)#return numner of rows inserted

        inserted_count = result.get("inserted_count", 0)
        return inserted_count 
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert cards: {str(e)}")

async def delete(repository : CardReferenceRepository, card_id: UUID)-> bool:
    try:
        result = await repository.delete(card_id)
        if not result:
            raise card_exception.CardDeletionError(f"Failed to delete card with ID {card_id}")
        return result
    except card_exception.CardDeletionError:
        raise
    except Exception as e:
        raise card_exception.CardDeletionError(f"Failed to delete card: {str(e)}")

async def get_many(repository: CardReferenceRepository
                   , card_ids: Sequence[UUID]
                   ) -> List[BaseCard]:
    try:
        results = await repository.list(card_id =card_ids)
        if not results:
            raise card_exception.CardNotFoundError(f"No cards found for IDs {card_ids}")
        return [BaseCard.model_validate(result) for result in results]
    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve cards: {str(e)}")

async def get_all(repository: CardReferenceRepository,
                ids: Optional[Sequence[UUID]] = None,
                limit: Annotated[int, Query(le=100)] = 100,
                offset: int = 0) -> List[BaseCard]:
    try:
        results = await repository.list( limit=limit, offset=offset)
        if not results:
            raise card_exception.CardNotFoundError("No cards found")
        cards = [BaseCard.model_validate(result) for result in results]
        return cards
    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve cards: {str(e)}")


async def get(repository: CardReferenceRepository,
               card_id: UUID,
                     ) -> BaseCard:
    try:
        result = await repository.get(
            card_id=card_id,
        )
        if not result:
            raise card_exception.CardNotFoundError(f"Card with ID {card_id} not found")
        return BaseCard.model_validate(result)
    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve card: {str(e)}")