from uuid import UUID
from fastapi import UploadFile
from automana.core.models.card_catalog.card import CreateCards
from automana.core.utils.utils import decode_json_input
from automana.core.models.card_catalog.set import NewSet, NewSets

async def cards_from_json(file: UploadFile):
    raw_cards = await decode_json_input(file)
    return CreateCards(items=raw_cards)

