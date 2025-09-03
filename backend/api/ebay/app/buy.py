from fastapi import APIRouter,  Depends, Query
from typing import List, Optional
from backend.modules.ebay.services import buy
from backend.modules.ebay.services import auth as authentificate

search_router = APIRouter(prefix='/search')

@search_router.get('/active')
async def make_get_request(token = Depends(authentificate.check_validity), 
                                      q: Optional[str] = None,
    category_ids: Optional[List[str]] = Query(default=None),
    charity_ids: Optional[List[str]] = Query(default=None),
    fieldgroups: Optional[List[str]] = Query(default=None),
    filter: Optional[List[str]] = Query(default=None),
    limit: Optional[int] = 50,
    offset: Optional[int] = 0):
    return await buy.make_active_listing_search(token , 
                                      q,
                                    category_ids,
                                    charity_ids,
                                    fieldgroups,
                                    filter,
                                    limit,
                                    offset)

@search_router.get('/sold')
async def make_sold_listing_search():
    pass