import json, httpx, os, time, ijson, logging, datetime, sys, glob

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from connection import get_connection
import pathlib, logging
from sqlalchemy import text

from urllib.parse import urlunsplit
from celery_main_app import celery_app
from typing import List, Dict, Optional




from backend.schemas.external_marketplace.shopify import shopify_theme

#test 

REQUESTS_PER_SECOND = 2
DELAY_BETWEEN_REQUESTS = 1 / REQUESTS_PER_SECOND

def create_url_query(scheme: str, netloc: str, path: str, query: str = None, fragment: str = None) -> str:
    """Create a complete URL from components"""
    return urlunsplit((scheme, netloc, path, query, fragment))

def rate_limited_request(url: str, headers: dict = None, timeout: float = 30.0) -> httpx.Response:
    """Make a rate-limited HTTP request"""
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        # Rate limiting: wait before allowing next request
        time.sleep(DELAY_BETWEEN_REQUESTS)
        return response
    except Exception as e:
        # Still wait even if request failed to maintain rate limit
        time.sleep(DELAY_BETWEEN_REQUESTS)
        raise e

def fetch_collections_page(api_url: str, page: int) -> Dict:
    """Fetch a single page of collections from Shopify API"""
    query_url = create_url_query(
        scheme='https',
        netloc=api_url,
        path='collections.json',
        query=f'limit=250&page={page}'
    )
    
    try:
        response = rate_limited_request(query_url)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise Exception(f"HTTP error fetching collections page {page}: {str(e)}")
    except Exception as e:
        raise Exception(f"Error fetching collections page {page}: {str(e)}")

def fetch_products_page(api_url: str, collection_handle: str, page: int) -> Dict:
    """Fetch a single page of products from a collection"""
    query_url = create_url_query(
        scheme='https',
        netloc=api_url,
        path=f'collections/{collection_handle}/products.json',
        query=f'limit=250&page={page}'
    )
    
    try:
        response = rate_limited_request(query_url)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise Exception(f"HTTP error fetching products page {page}: {str(e)}")
    except Exception as e:
        raise Exception(f"Error fetching products page {page}: {str(e)}")


def save_data_to_file(data: Dict, filepath: str):
    """Save data to JSON file with proper formatting"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def is_mtg_collection(api_url: str, collection_handle: str, target_product_type: str = "MTG Single") -> bool:
    """Check if a collection contains MTG products by sampling the first product with rate limiting"""
    try:
        query_url = create_url_query(
            scheme='https',
            netloc=api_url,
            path=f'collections/{collection_handle}/products.json',
            query='limit=1'
        )
        
        response = rate_limited_request(query_url, timeout=10.0)
        response.raise_for_status()
        
        data = response.json()
        products = data.get('products', [])
        
        if not products:
            return False
            
        return products[0].get('product_type', '').strip() == target_product_type
        
    except Exception:
        return False  # Assume not MTG if we can't determine


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def download_good_game_data(self, target_path: str):
    """Download Good Game Gaming data with rate limiting (2 requests per second)"""
    start_time = time.time()
    request_count = 0
    
    # for each shop in the db, update the collections name
    # for drafting, just get the most recent market
    markets = []
    query = """
    SELECT DISTINCT ON (market_id) market_id, api_url, updated_at 
    FROM markets.market_ref 
    WHERE name = 'Good Game Gaming'
    ORDER BY market_id, updated_at DESC
    """
    from backend.database.get_database import get_connection as async_raw_get_connection

    with async_raw_get_connection() as conn:
        result = conn.execute(text(query))
        markets = [dict(row._mapping) for row in result.fetchall()]
    
    if not markets:
        logging.warning("No Good Game Gaming markets found in database")
        return {"status": "no_markets", "message": "No markets found"}
    
    logging.info(f"Starting download for {len(markets)} markets with rate limit: {REQUESTS_PER_SECOND} req/sec")
    
    # get the collections for each market
    for market in markets:
        market_id = market.get('market_id')
        api_url = market.get('api_url')

        logging.info(f"Processing market {market_id}: {api_url}")

        # Save collections to folder
        market_path = pathlib.Path(target_path) / f"collections/{market_id}_{datetime.datetime.now().strftime('%Y%m%d')}"
        market_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Fetch collections from Shopify API with rate limiting
            collection_index = 1  # Fixed: Shopify pagination starts at 1
            total_collections = []
            
            logging.info(f"Fetching collections for market {market_id}...")
            
            while True:
                try:
                    # Use the rate-limited fetch function
                    collections_data = fetch_collections_page(api_url, collection_index)
                    request_count += 1
                    
                    collections = collections_data.get('collections', [])
                    if not collections:
                        logging.info(f"Market {market_id} - No more collections to fetch at page {collection_index}")
                        break
                    
                    total_collections.extend(collections)
                    logging.info(f"Market {market_id} - Fetched {len(collections)} collections (page {collection_index})")
                    collection_index += 1
                    
                except Exception as e:
                    logging.error(f"Market {market_id} - Failed to fetch collections page {collection_index}: {str(e)}")
                    break
            
            logging.info(f"Market {market_id} - Total collections found: {len(total_collections)}")
            
            # Process each collection with rate limiting
            for idx, collection in enumerate(total_collections):
                if collection.get("products_count", 0) == 0:
                    continue

                collection_id = collection.get('id')
                collection_name = collection.get('handle')
                
                logging.info(f"Processing collection {idx+1}/{len(total_collections)}: {collection_name} ({collection.get('products_count')} products)")

                # Create collection directory
                collection_dir = market_path / f"{collection_name}_{collection_id}"
                collection_dir.mkdir(parents=True, exist_ok=True)
                
                # Save collection metadata
                collection_file = collection_dir / "collection.json"
                save_data_to_file(collection, str(collection_file))
                
                # Check if it's MTG collection first (with rate limiting)
                try:
                    is_mtg = is_mtg_collection(api_url, collection_name)
                    request_count += 1
                    
                    if not is_mtg:
                        logging.info(f"Skipping non-MTG collection: {collection_name}")
                        continue
                        
                    logging.info(f"MTG collection detected: {collection_name} - fetching products...")
                    
                except Exception as e:
                    logging.warning(f"Could not determine collection type for {collection_name}: {str(e)}")
                    # Continue anyway
                
                # Fetch and save products for the collection with rate limiting
                try:
                    product_index = 1  # Fixed: Shopify pagination starts at 1
                    all_products = []
                    
                    while True:
                        try:
                            # Use the rate-limited fetch function
                            products_data = fetch_products_page(api_url, collection_name, product_index)
                            request_count += 1
                            
                            products_batch = products_data.get('products', [])
                            
                            if not products_batch:
                                logging.info(f"All products fetched for collection {collection_name}")
                                break
                                
                            all_products.extend(products_batch)
                            logging.info(f"Fetched {len(products_batch)} products (page {product_index}) for {collection_name}")

                            if len(products_batch) < 250:
                                # Last page reached
                                break
                            product_index += 1
                            
                        except Exception as e:
                            logging.error(f"Failed to fetch products for {collection_name} page {product_index}: {str(e)}")
                            break
                    
                    # Save all products at once
                    if all_products:
                        products_file = collection_dir / "products.json"
                        save_data_to_file({"products": all_products}, str(products_file))
                        
                        logging.info(f"✅ Saved {len(all_products)} total products for collection {collection_name}")

                except Exception as e:
                    logging.error(f"Exception fetching products for collection {collection_id}: {str(e)}")
                    
        except Exception as e:
            logging.error(f"Market {market_id} - Exception during fetch: {str(e)}")
    
    # Calculate statistics
    end_time = time.time()
    duration = end_time - start_time
    actual_rate = request_count / duration if duration > 0 else 0
    
    result = {
        "status": "success", 
        "markets_processed": len(markets),
        "total_requests": request_count,
        "duration_seconds": round(duration, 2),
        "actual_request_rate": round(actual_rate, 2),
        "target_request_rate": REQUESTS_PER_SECOND,
        "message": f"Successfully processed {len(markets)} markets with {request_count} API calls"
    }
    
    logging.info(f"Download completed: {json.dumps(result, indent=2)}")
    return result

import asyncio
from backend.new_services.app_integration.shopify.data_staging_service import (
    process_json_dir_to_parquet,
    stage_data_from_parquet,
    upload_all_json_in_directory,
    get_market_id
)


def sync_get_market_id(market_repository, code: str) -> int:
    """Sync wrapper for get_market_id"""
    return asyncio.run(get_market_id(market_repository, code))

def sync_process_json_dir_to_parquet(market_repository, path_to_json: str, market_code: str, output_path: str):
    """Sync wrapper for process_json_dir_to_parquet"""
    return asyncio.run(process_json_dir_to_parquet(market_repository, path_to_json, market_code, output_path))

def sync_stage_data_from_parquet(product_repository, parquet_base_path: str, batch_size: int = 10000):
    """Sync wrapper for stage_data_from_parquet"""
    return asyncio.run(stage_data_from_parquet(product_repository, parquet_base_path, batch_size))

def sync_upload_all_json_in_directory(absolute_path: str, market_id: str, app_id: str, repository, batch_size: int = 1000, product_currency='AUD'):
    """Sync wrapper for upload_all_json_in_directory"""
    return asyncio.run(upload_all_json_in_directory(absolute_path, market_id, app_id, repository, batch_size, product_currency))


import functools, requests

@functools.lru_cache(maxsize=365)
def fetch_fx_rate(from_currency: str, to_currency: str, date_str: str, app_id : str) -> float:
    
    # example using exchangerate.host
    resp = requests.get(
        f"https://openexchangerates.org/api/historical/{date_str}.json" ,
        params={"app_id": app_id },
        timeout=5,
    )
    resp.raise_for_status()
    from_rate = resp.json()["rates"][from_currency]
    to_rate = resp.json()["rates"][to_currency]
    rate = to_rate / from_rate
    return rate

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_shopify_json_to_parquet(self, json_directory: str, market_code: str, output_path: str):
    """Process JSON files and convert them to Parquet format"""
    task_id = self.request.id
    start_time = datetime.datetime.utcnow()
    
    logging.info(f"Starting JSON to Parquet conversion task {task_id}")
    logging.info(f"JSON directory: {json_directory}")
    logging.info(f"Market code: {market_code}")
    logging.info(f"Output path: {output_path}")
    
    async def run_async_task():
        from backend.repositories.app_integration.shopify.market_repository import MarketRepository
        from backend.database.get_database import get_async_pool_connection
        from backend.request_handling.QueryExecutor import AsyncQueryExecutor
    
        # Use the async context manager properly
        async with get_async_pool_connection() as conn:
            query_executor = AsyncQueryExecutor()
            market_repository = MarketRepository(conn, query_executor)
            
            # Use the async function directly
            await process_json_dir_to_parquet(
                market_repository=market_repository,
                path_to_json=json_directory,
                market_code=market_code,
                output_path=output_path
            )

    try:
        # Run the async function with asyncio.run()
        asyncio.run(run_async_task())
        
        end_time = datetime.datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Count output files
        product_dirs = [d for d in glob.glob(os.path.join(output_path, "*")) if os.path.isdir(d)]
        
        result = {
            "status": "completed",
            "task_id": task_id,
            "json_directory": json_directory,
            "output_path": output_path,
            "market_code": market_code,
            "statistics": {
                "products_processed": len(product_dirs),
                "duration_seconds": round(duration, 2)
            },
            "timestamp": end_time.isoformat()
        }
        
        logging.info(f"JSON to Parquet conversion completed")
        return result
        
    except Exception as e:
        error_msg = f"JSON to Parquet conversion failed: {str(e)}"
        logging.error(error_msg)
        return {
            "status": "failed",
            "task_id": task_id,
            "error": error_msg,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }