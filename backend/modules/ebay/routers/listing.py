from backend.modules.ebay.models import auth as auth_model, listings as listings_model
from backend.modules.ebay.services import listings
from fastapi import APIRouter, HTTPException, Query
from typing import Annotated


ebay_listing_router = APIRouter(prefix='/listing', tags=['listings'])

@ebay_listing_router.get("/active", response_model=listings_model.ActiveListingResponse)
async def do_api_call(token, limit : Annotated[int , Query(gt=1, le=50)] , offset :  Annotated[int , Query(gt=1,)]): 
    active_listings : listings_model.ActiveListingResponse = await listings.obtain_all_active_listings(token)
    return active_listings


@ebay_listing_router.get('/{listing_id}')
async def getActiveListing():
    raise HTTPException(status_code=400, detail='Not implemented')