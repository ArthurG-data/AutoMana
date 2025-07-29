from uuid import UUID
from fastapi import UploadFile
from backend.schemas.card_catalog.card import CreateCards
from backend.shared.utils import decode_json_input
from backend.schemas.card_catalog.set import NewSet, NewSets

async def cards_from_json(file: UploadFile):
    raw_cards = await decode_json_input(file)
    return CreateCards(items=raw_cards)

async def sets_from_json(file: UploadFile)->NewSets:
    raw_sets = await decode_json_input(file)
    return NewSets(items=raw_sets)