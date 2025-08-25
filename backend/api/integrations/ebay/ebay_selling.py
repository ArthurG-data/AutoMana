from backend.schemas.app_integration.ebay import  listings as listings_model
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Annotated, List
from backend.dependancies.service_deps import get_current_active_user, get_service_manager
from backend.new_services.service_manager import ServiceManager


ebay_listing_router = APIRouter(prefix='/listing', tags=['listings'])

"""
@ebay_listing_router.get("/active/bulk", response_model=listings_model.ActiveListingResponse, description='get all the active listings')#chnege the location
async def do_api_call(limit : Annotated[int , Query(gt=1, le=50)]=10 
                      , offset :  Annotated[int , Query(ge=0,)]=0
                      , service_manager : ServiceManager = Depends(get_service_manager)
                      , user = Depends(get_current_active_user)
                      ): 
    try:
       listings = await service_manager.execute_service(
           'integration.ebay.listings'
           ,)
       active_listings : listings_model.ActiveListingResponse = await listings.obtain_all_active_listings(token.access_token)   
    return active_listings

@ebay_listing_router.get("/active/{item_id}", description='get a specific listing')
async def do_api_call(item_id : str, token = Depends(authentificate.check_validity)):
    return await listings.obtain_item(token.access_token, item_id)

"""
@ebay_listing_router.post("/", description="posting a new listing")
async def do_api_call(listing : listings_model.ItemModel, token = Depends(authentificate.check_validity)):
    try:
        result = await ServiceManager.execute_service(
            "integrations.ebay.selling",
            action="create",
            payload=listing,
            #environment=environment
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

"""
@ebay_listing_router.put("/active/{item_id}", description="updates a item")
async def do_api_call(updatedItem : listings_model.ItemModel,item_id : str,  token = Depends(authentificate.check_validity)):
    if updatedItem.ItemID != item_id:
        raise HTTPException(status_code=400, detail="Item ID in URL and body must match")
    return await listings.update_listing(updatedItem, token.access_token)

@ebay_listing_router.get("/active/", response_model=listings_model.ActiveListingResponse, description='get a specific listing')
async def do_api_call(token = Depends(authentificate.check_validity), item_ids = Annotated[List[str], Query()]):
    pass
"""                   