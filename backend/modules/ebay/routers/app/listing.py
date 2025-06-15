from backend.modules.ebay.models import auth as auth_model, listings as listings_model
from backend.modules.ebay.services import listings, auth as authentificate
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Annotated, List



ebay_listing_router = APIRouter(prefix='/listing', tags=['listings'])

@ebay_listing_router.get("/active/bulk", response_model=listings_model.ActiveListingResponse, description='get all the active listings')#chnege the location
async def do_api_call(limit : Annotated[int , Query(gt=1, le=50)]=10 , offset :  Annotated[int , Query(ge=0,)]=0, token = Depends(authentificate.check_validity)): 
    active_listings : listings_model.ActiveListingResponse = await listings.obtain_all_active_listings(token.access_token)
    return active_listings

@ebay_listing_router.get("/active/{item_id}", description='get a specific listing')
async def do_api_call(item_id : str, token = Depends(authentificate.check_validity)):
    return await listings.obtain_item(token.access_token, item_id)
  
@ebay_listing_router.post("/", description="posting a new listing")
async def do_api_call(listing : listings_model.CardListing, token = Depends(authentificate.check_validity)):
    return await listings.add_or_verify_post_new_item(listing , token.access_token)

@ebay_listing_router.put("/active/{item_id}", description="updates a item")
async def do_api_call(updatedItem : listings_model.ListingUpdate,  token = Depends(authentificate.check_validity)):
    return await listings.update_listing(updatedItem, token)

@ebay_listing_router.get("/active/", response_model=listings_model.ActiveListingResponse, description='get a specific listing')
async def do_api_call(token = Depends(authentificate.check_validity), item_ids = Annotated[List[str], Query()]):
    pass
                      