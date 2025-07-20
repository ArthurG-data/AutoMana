from uuid import UUID
import json
from fastapi import UploadFile
from backend.schemas.card_catalog.card import CreateCards
from backend.shared.utils import decode_json_input

def to_json_safe(data):
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, UUID):
            return str(obj)
        else:
            return obj
    return json.dumps(clean(data))

async def cards_from_json(file: UploadFile):
    raw_cards = await decode_json_input(file)
    return CreateCards(items=raw_cards)