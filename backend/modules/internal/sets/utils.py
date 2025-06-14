from typing import List
from pydantic import ValidationError
from backend.modules.internal.sets.models import NewSet, NewSets
from fastapi import UploadFile
from backend.shared.utils import decode_json_input

def filter_valid_sets(raw_items: List[dict]) -> tuple[List[NewSet], List[dict]]:
    valid_sets = []
    invalid_sets = []
    
    for raw in raw_items:
        try:
            new_set = NewSet(**raw)
            valid_sets.append(new_set)
        except ValidationError:
            invalid_sets.append(raw)
    
    return valid_sets, invalid_sets
    
async def sets_from_json(file: UploadFile)->NewSets:
    raw_sets = await decode_json_input(file)
    return NewSets(items=raw_sets)