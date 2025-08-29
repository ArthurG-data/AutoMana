import token
from backend.schemas.app_integration.ebay import  listings as listings_model
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Annotated, List
from backend.dependancies.service_deps import get_current_active_user, get_service_manager
from backend.new_services.service_manager import ServiceManager
from backend.request_handling.StandardisedQueryResponse import ApiResponse,PaginatedResponse,PaginationInfo


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
async def do_api_call(listing : listings_model.ItemModel, 
                      app_code : str = Query(..., description="The application code for the eBay integration"),
                      user = Depends(get_current_active_user),
                      service_manager : ServiceManager = Depends(get_service_manager),

                      ):
    try:
        payload = {
            "item": listing,
            "app_code": app_code,
            "user_id": user.unique_id
        }
        result = await service_manager.execute_service(
            "integrations.ebay.selling",
            action="create",
            payload=payload,
            #environment=environment
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ebay_listing_router.get('/active', description='get the active listings of a user'""", response_model=PaginatedResponse""")
async def do_api_call( limit: Annotated[int, Query(gt=0, le=100)] = 10,
                        offset: Annotated[int, Query(ge=0)] = 0,
                        app_code = str,
                        user = Depends(get_current_active_user),
                        service_manager = Depends(get_service_manager)
                        ):
    try:
        env = await service_manager.execute_service(
            "integrations.ebay.get_environment",
            app_code=app_code,
            user_id=user.unique_id
        )
        if not env:
            raise HTTPException(status_code=404, detail="Environment not found")
        result = await service_manager.execute_service(
            "integrations.ebay.selling",
            action="get_active",
            environment=env,
            payload={
                "app_code": app_code,
                "user_id": user.unique_id,
                "limit": limit,
                "offset": offset
            }
        )
   
        result = listings_model.ActiveListingResponse(items=result['GetMyeBaySellingResponse']['ActiveList']['ItemArray']['Item'])
        return PaginatedResponse(
            message="Active listings retrieved successfully",
            data=result.items,
            pagination=PaginationInfo(
                limit=limit,
                offset=offset,
                total_count=len(result.items),
                has_next=offset + limit < len(result.items),
                has_previous=offset > 0
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ebay_listing_router.get('/history', description='get the history of a listing', response_model=PaginatedResponse)
async def do_api_call(limit: Annotated[int, Query(gt=0, le=100)] = 10,
                        offset: Annotated[int, Query(ge=0)] = 0,
                        app_code = str,
                        user = Depends(get_current_active_user),
                        service_manager = Depends(get_service_manager)):
    try:
        env = await service_manager.execute_service(
            "integrations.ebay.get_environment",
            app_code=app_code,
            user_id=user.unique_id
        )
        if not env:
            raise HTTPException(status_code=404, detail="Environment not found")
        result = await service_manager.execute_service(
            "integrations.ebay.selling",
            action="get_history",
            environment=env,
            payload={
                "app_code": app_code,
                "user_id": user.unique_id,
                "limit": limit,
                "offset": offset
            }
        )
        validated_result = listings_model.ListingHistoryResponse.model_validate(result)
        return PaginatedResponse(
            message="History retrieved successfully",
            data=validated_result.orders,
            pagination=PaginationInfo(
                limit=validated_result.limit,
                offset=validated_result.offset,
                total_count=len(validated_result),
                has_next=offset + limit < len(validated_result),
                has_previous=offset > 0
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ebay_listing_router.put("/{item_id}", description="updates a item")
async def do_api_call(updatedItem : listings_model.ItemModel
                      ,item_id : str
                      , app_code = str,
                    user = Depends(get_current_active_user),
                    service_manager = Depends(get_service_manager)):
    if updatedItem.ItemID != item_id:
        raise HTTPException(status_code=400, detail="Item ID in URL and body must match")
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling",
            action="update",
            payload={
                "app_code": app_code,
                "user_id": user.unique_id,
                "item": updatedItem
            }
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
