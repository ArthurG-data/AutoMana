
from psycopg2.extras import  Json
from uuid import UUID
from datetime import datetime
from fastapi import Query
from backend.repositories.card_catalog import card_queries as queries 
from backend.schemas.card_catalog import card as card_schemas
from backend.utils_new.card_catalog import data_transformer as utils
from backend.repositories.card_catalog.card_repository import CardReferenceRepository
from typing import Annotated, Sequence, Optional, List
from backend.schemas.card_catalog.card import BaseCard
from backend.exceptions.service_layer_exceptions.card_catalogue import card_exception
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def add(card_repository : CardReferenceRepository
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
        card = await card_repository.add(values)
        return card_schemas.BaseCard.model_validate(card)
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert card: {str(e)}")

async def add_many(card_repository : CardReferenceRepository, values_list : card_schemas.CreateCards):
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
        result = await card_repository.add_many(cards)#return numner of rows inserted

        inserted_count = result.get("inserted_count", 0)
        return inserted_count 
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert cards: {str(e)}")

async def delete(card_repository : CardReferenceRepository, card_id: UUID)-> bool:
    try:
        result = await card_repository.delete(card_id)
        if not result:
            raise card_exception.CardDeletionError(f"Failed to delete card with ID {card_id}")
        return result
    except card_exception.CardDeletionError:
        raise
    except Exception as e:
        raise card_exception.CardDeletionError(f"Failed to delete card: {str(e)}")

async def search_cards(card_repository: CardReferenceRepository
                   , name: Optional[str] = None
                   , color: Optional[str] = None
                   , rarity: Optional[str] = None
                   , card_id: Optional[UUID] = None
                   , released_at: Optional[datetime] = None
                   , set_name: Optional[str] = None
                   , mana_cost: Optional[int] = None
                   , digital: Optional[bool] = None
                   , card_type: Optional[str] = None
                   # Pagination
                   , limit: int = 100
                   , offset: int = 0
                   , sort_by: str = "name"
                   , sort_order: str = "asc"
                   ) -> List[BaseCard]:
    logger.info(f"Searching for cards with: name={name}, color={color}, rarity={rarity}, card_id={card_id}, set_name={set_name}, mana_cost={mana_cost}, digital={digital}")
    try:
        if card_id:
            logger.info(f"Fetching card by ID: {card_id}")
            card = card_repository.get(card_id)
            if not card:
                return {"users": [], "total": 0}
            return {"users": [BaseCard.model_validate(card)]
                    , "total": 1
                    }

        result = await card_repository.search(name=name,
                                               color=color,
                                               rarity=rarity,
                                               released_at=released_at,
                                               set_name=set_name,
                                               mana_cost=mana_cost,
                                               digital=digital,
                                               limit=limit,
                                               offset=offset,
                                               sort_by=sort_by,
                                               card_type=card_type,
                                               sort_order=sort_order)
        if not result:
            raise card_exception.CardNotFoundError(f"No cards found for IDs {card_id}")
        cards = result.get("cards", [])
        total_count = result.get("total_count", 0)
        return  {
            "cards": cards,
            "total_count": total_count
        }

    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve cards: {str(e)}")


async def get(card_repository: CardReferenceRepository,
               card_id: UUID,
                     ) -> BaseCard:
    try:
        result = await card_repository.get(
            card_id=card_id,
        )
        if not result:
            raise card_exception.CardNotFoundError(f"Card with ID {card_id} not found")
        return BaseCard.model_validate(result)
    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve card: {str(e)}")