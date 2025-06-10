from fastapi import APIRouter, Query
from backend.modules.public.sets.models import SetwCount
from backend.modules.public.sets.services import retrieve_set
from typing import List, Annotated
from uuid import UUID
from backend.database.get_database import cursorDep

router = APIRouter(
        tags=['sets'], 
        responses={404:{'description':'Not found'}}
        
)

@router.get('/{set_id}', response_model=SetwCount)
async def get_set(set_id : UUID, connection: cursorDep):
    return  retrieve_set(connection, ids=set_id, select_all=False )

@router.get('/', response_model=List[SetwCount])
async def get_sets(connection: cursorDep,
                    limit : Annotated[int, Query(le=100)]=100,
                    offset: int =0,
                    set_ids : Annotated[List[str],Query(title='Optional set_is')]=None):
     return  retrieve_set(connection, ids=set_ids,  limit=limit, offset=offset, select_all=True)

