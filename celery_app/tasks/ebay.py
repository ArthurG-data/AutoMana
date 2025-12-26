import json, logging, datetime, redis
from typing import List, Optional
#from backend.repositories.app_integration.ebay import auth_repository
#from backend.schemas.auth.cookie import RefreshTokenResponse
from main import celery_app
from celery_app.ressources import get_connection
#from backend.request_handling.QueryExecutor import SQLAlchemyQueryExecutor
#from backend.new_services.analysis.pricing import enhanced_pricing_analysis
#to do, create a user for the task manager
redis_client = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)

#task to check prices for a card in collection , using ebay browse api
#from backend.schemas.app_integration.ebay.auth import TokenResponse
from datetime import datetime, timedelta

'''
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def get_or_refresh_ebay_token(self, app_code, user_id= None) :
    """
    Get eBay access token from Redis or refresh if expired
    """
    if user_id:
        cache_key = f"ebay_token:user:{user_id}"
    else:
        cache_key = f"ebay_token:system:{app_code}"
    
    try:
        token_data_json = redis_client.get(cache_key)
        if token_data_json:
            token_data = json.loads(token_data_json)
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if expires_at > datetime.utcnow():
                logging.info(f"Using cached eBay token for {cache_key}")
                return token_data["access_token"]
        from backend.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
        from backend.repositories.app_integration.ebay.ApiAuth_repository import EbayAuthAPIRepository
       

        with get_connection() as conn:
            query_executor = SQLAlchemyQueryExecutor()
            auth_repo = EbayAuthRepository(conn, query_executor)
            api_repo = EbayAuthAPIRepository(environment="production")
        
            stored_access_token = auth_repo.get_valid_access_token_sync(app_code, user_id) if user_id else None
            if not stored_access_token:
                logging.info(f"No stored access token found for user {user_id}, refreshing...")
                refresh_token = auth_repo.get_access_from_refresh(app_code, user_id)
            if not refresh_token:
                raise ValueError("No valid refresh token found")

            settings = auth_repo.get_app_settings_sync(user_id=user_id, app_code=app_code)
            if settings is None:
                raise ValueError(f"No settings found for app_code: {app_code} and user_id: {user_id}")
            logging.info(f"Using the settings {settings} to refresh eBay token for {cache_key}")
            scopes = auth_repo.get_app_scopes_sync(app_id=settings["app_id"])

            refresh_result = api_repo.exchange_refresh_token_sync(
                        refresh_token=refresh_token,
                        app_id=settings["app_id"],
                        secret=settings["decrypted_secret"],
                        scope=scopes if scopes else []
                    )
            if not refresh_result.get("access_token"):
                raise ValueError("Failed to refresh eBay token - no access token returned")
            logging.info(f"Refresh result: {refresh_result}")
        token_cache_data = {
                "access_token": refresh_result['access_token'],
                "expires_at": refresh_result.get('expires_on'),
                "refreshed_at": datetime.utcnow().isoformat()
            }
        redis_client.setex(
            cache_key,
            refresh_result["expires_in"],
            json.dumps( token_cache_data)
        )
        if not refresh_result.get("access_token"):
            raise ValueError("No valid access token found")
        return refresh_result["access_token"]
    
    except Exception as e:
        logging.error(f"❌ Failed to get eBay token for {cache_key}: {str(e)}")
        raise
""""""
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
"""
'''