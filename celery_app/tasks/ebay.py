from typing import List, Optional
import datetime
import logging
from celery_main_app import celery_app
from backend.new_services.analysis.pricing import enhanced_pricing_analysis

#to do, create a user for the task manager


#task to check prices for a card in collection , using ebay browse api




@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def refresh_ebay_token(self, user_id: int = None, app_code: str = "default"):
    """
    Task to refresh eBay access token and cache it in Redis
    Can be used for specific user or system-wide token
    """
    task_id = self.request.id
    start_time = datetime.utcnow()
    
    logging.info(f"Token refresh task {task_id} started for user {user_id}, app_code {app_code}")
    
    async def refresh_token_async():
        try:
            from backend.repositories.app_integration.ebay.ApiAuth_repository import EbayAuthRepository
            auth_repo = EbayAuthRepository(environment="production")
            
            if user_id:
                # Get user-specific token from database
                token_data = await get_user_ebay_token(user_id)
                if not token_data or not token_data.refresh_token:
                    raise ValueError(f"No refresh token found for user {user_id}")
                
                # Refresh user token
                new_token = await auth_repo.refresh_access_token(token_data.refresh_token)
                
                # Update database
                await update_user_ebay_token(user_id, new_token)
                
                # Cache in Redis with user-specific key
                cache_key = f"ebay_token:user:{user_id}"
            else:
                # System-wide token (app-level)
                system_refresh_token = await get_system_ebay_token(app_code)
                if not system_refresh_token:
                    raise ValueError(f"No system refresh token found for app_code {app_code}")
                
                new_token = await auth_repo.refresh_access_token(system_refresh_token)
                
                # Cache in Redis with system-level key
                cache_key = f"ebay_token:system:{app_code}"
            
            # Cache token in Redis with expiry
            token_cache_data = {
                "access_token": new_token.access_token,
                "expires_at": (datetime.utcnow() + timedelta(seconds=new_token.expires_in)).isoformat(),
                "token_type": new_token.token_type,
                "refreshed_at": datetime.utcnow().isoformat()
            }
            
            # Set with expiry (refresh 5 minutes before actual expiry)
            redis_client.setex(
                cache_key, 
                new_token.expires_in - 300,  # 5 minutes buffer
                json.dumps(token_cache_data)
            )
            
            logging.info(f"Token refreshed and cached for {cache_key}")
            return token_cache_data
            
        except Exception as e:
            logging.error(f"Token refresh failed: {str(e)}")
            raise
    
    import asyncio
    try:
        result = asyncio.run(refresh_token_async())
        end_time = datetime.utcnow()
        logging.info(f"Token refresh completed in {(end_time - start_time).total_seconds()} seconds")
        return result
    except Exception as e:
        logging.error(f"Token refresh task failed: {str(e)}")
        raise


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ebay_search_price(
                     #app_code: str,
                     self,
                     q: Optional[str] = None,
                     gtin: Optional[str] = None,
                     charity_ids: Optional[List[str]] = None,
                     fieldgroups: Optional[List[str]] = None,
                     compatibility_filter: Optional[str] = None,
                     auto_correct: Optional[str] = None,
                     category_ids: Optional[List[str]] = None,
                     filter: Optional[List[str]] = None,
                     sort: Optional[str] = None,
                     limit: Optional[int] = 50,
                     offset: Optional[int] = 0,
                     aspect_filter: Optional[str] = None,
                     epid: Optional[str] = None
):
    #task_id = self.request.id else "unknown"
    task_id = self.request.id
    start_time = datetime.datetime.utcnow()

    #logging.info(f"Task {task_id} started at {start_time.isoformat()} for app_code {app_code}")
    from backend.request_handling.StandardisedQueryResponse import PaginatedResponse, PaginationInfo
    async def run_async_task():
        from backend.repositories.app_integration.ebay.ApiBrowse_repository import EbayBrowseAPIRepository
        from backend.new_services.app_integration.ebay.browsing_services import search_items
        repo = EbayBrowseAPIRepository(environment="production")
        result = await search_items(
            repo,
            test_token,
            q=q,
            gtin=gtin,
            charity_ids=charity_ids,
            fieldgroups=fieldgroups,
            compatibility_filter=compatibility_filter,
            auto_correct=auto_correct,
            category_ids=category_ids,
            filter=filter,
            sort=sort,
            limit=limit,
            offset=offset,
            aspect_filter=aspect_filter,
            epid=epid
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
    
    import asyncio
    import nest_asyncio
    nest_asyncio.apply()
    try:
        results = asyncio.run(run_async_task())
        end_time = datetime.datetime.utcnow()
        logging.info(f"Task completed at {end_time.isoformat()}, duration: {(end_time - start_time).total_seconds()} seconds")
        return results
    except Exception as e:
        logging.error(f"Task failed with exception: {str(e)}")
        raise e
 

#analyse results
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def analyze_results(self, results):
    # Perform analysis on the results
    pass

#task to update ebay listings for a card in collection

#task to post a new listing 

#task to remove or suspend a listing

#task to go through all items in collection