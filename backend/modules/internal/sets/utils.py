from typing import List
from pydantic import ValidationError
from backend.modules.internal.sets.models import NewSet, NewSets
import json
from fastapi import UploadFile

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

async def decode_json_input(file: UploadFile)-> dict:
    content = await file.read()
    try:
        #decode bytes
        decoded_content = content.decode("utf-8")
        data = json.loads(decoded_content)
        data= data.get('data')
        return data
    except Exception as e:
        return [f"Error: {str(e)}"]
    
async def sets_from_json(file: UploadFile):
    raw_sets = await decode_json_input(file)
    return NewSets(items=raw_sets)