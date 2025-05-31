from typing import List
from pydantic import ValidationError
from backend.modules.internal.sets.models import NewSet, NewSets

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