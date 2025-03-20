import logging
from fastapi import APIRouter, Depends, Path, HTTPException, Query
from typing import Annotated
from backend.dependancies import get_token_header
from backend.models.cards import BaseCard
from backend.database import execute_query
from backend.dependancies import cursorDep


router = APIRouter(
    prefix='/cards',
    tags=['cards'],
    dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)

@router.get('/{card_id}', response_model=list[BaseCard])
async def read_card(card_id : Annotated[str, Path(title='The unique version id of the card to get', min_length=36, max_length=36)],  connection: cursorDep ) -> list[BaseCard] | dict :
    query =  """ SELECT * FROM card_version WHERE card_version_id = %s """ 
    logging.info("🔹 Route handler started!")
    try:
        cards =  execute_query(connection, query, (card_id,), fetch=True)
        if cards:
            return cards
        else :
            raise HTTPException(status_code=404, detail="Card ID not found")
    except Exception as e:
        return {'card-id' : card_id, 'error':str(e)}
    
class CommonQueryParams:
    def __init__ (self, q : str | None=None, skip: Annotated[int, Query(ge=0)] =0, limit: Annotated[int , Query(ge=1, le=50)]= 10):
        self.q = q,
        self.skip = skip,
        self.limit = limit
     
@router.get('/', response_model=list[BaseCard]) 
async def read_card(commons: Annotated[CommonQueryParams, Depends(CommonQueryParams)], connection : cursorDep):
    query = """ SELECT * FROM card_version LIMIT %s OFFSET %s """
    try:
        cards =  execute_query(connection, query, (commons.limit, commons.skip), fetch=True)
        return cards
    except Exception as e:
        return {'error':str(e)}
