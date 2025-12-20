from fastapi import APIRouter,  Depends, Query, Request, HTTPException
from typing import List, Optional
import logging
from backend.dependancies.service_deps import ServiceManagerDep
from backend.new_services.app_integration.ebay import buying_services
from backend.schemas.app_integration.ebay import listings as listings_model
from backend.request_handling.StandardisedQueryResponse import PaginatedResponse, PaginationInfo
#from backend.modules.ebay.services import auth as authentificate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

search_router = APIRouter(prefix='/search')
#test without dependency first
@search_router.get('/', response_model=PaginatedResponse)
async def make_get_request(    
                            service_manager: ServiceManagerDep, 
                            app_code: str = Query(...),
                            q: Optional[str] = Query(None),
                            gtin: Optional[str] = Query(None),
                            charity_ids: Optional[List[str]] = Query(None),
                            fieldgroups: Optional[List[str]] = Query(None),
                            compatibility_filter: Optional[str] = Query(None),
                            auto_correct: Optional[str] = Query(None),
                            category_ids: Optional[List[str]] = Query(None),
                            filter: Optional[List[str]] = Query(None),
                            sort: Optional[str] = Query(None),
                            limit: Optional[int] = Query(50),
                            offset: Optional[int] = Query(0),
                            aspect_filter: Optional[str] = Query(None),
                            epid: Optional[str] = Query(None),
        
):
    try:
        if not q:
            raise ValueError("Query parameter 'q' is required")
        
        token = await service_manager.execute_service(
            "integrations.ebay.get_token",
            app_code=app_code
        )
        if not token or len(token) == 0:
            logger.error(f"Failed to retrieve access token for app code {app_code}")
            raise ValueError("Failed to retrieve eBay access token")

        environment = await service_manager.execute_service(
            "integrations.ebay.get_environment",
            app_code=app_code
        )
        result : listings_model.SearchResult = await service_manager.execute_service(
            "integrations.ebay.search",
            token=token,
            q=q,
            gtin=gtin,
            epid=epid,
            compatibility_filter=compatibility_filter,
            auto_correct=auto_correct,
            aspect_filter=aspect_filter,
            sort=sort,
            category_ids=category_ids,
            charity_ids=charity_ids,
            fieldgroups=fieldgroups,
            filter=filter,
            limit=limit,
            offset=offset,
            environment = environment
        )
        return PaginatedResponse(
            data=result.itemSummaries,
            pagination=PaginationInfo(
                total_count=len(result),
                limit=limit,
                offset=offset,
                has_next=offset + limit < len(result),
                has_previous=offset > 0
            )
        )
    except HTTPException:
        raise
    return await buying_services.make_active_listing_search(service_manager,
                                      q,
                                    category_ids,
                                    charity_ids,
                                    fieldgroups,
                                    filter,
                                    limit,
                                    offset)
