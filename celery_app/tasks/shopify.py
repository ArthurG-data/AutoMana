import json
from connection import get_connection
from http_utils import get
import pathlib, logging
from sqlalchemy import text
import datetime

from celery_main_app import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def download_good_game_data(self, target_path: str):
    # for each shop in the db, update the collections name
    # for drafting, just get the most recent market
    markets = []
    query = """
    SELECT DISTINCT ON (market_id) market_id, api_url, updated_at 
    FROM markets.market_ref 
    WHERE name = 'Good Game Gaming'
    ORDER BY market_id, updated_at DESC
    """
    
    with get_connection() as conn:
        result = conn.execute(text(query))
        markets = [dict(row._mapping) for row in result.fetchall()]
    
    if not markets:
        logging.warning("No Good Game Gaming markets found in database")
        return {"status": "no_markets", "message": "No markets found"}
    
    # get the collections for each market
    for market in markets:
        market_id = market.get('market_id')
        api_url = market.get('api_url')

        # Fixed: Remove extra space before comment
        # Save collections to folder
        market_path = pathlib.Path(target_path) / f"collections/{market_id}_{datetime.datetime.now().strftime('%Y%m%d')}"
        market_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Fetch collections from Shopify API
            # loop until all collections found
            collection_index = 0  # Fixed: Use different variable name
            total_collections = []
            
            while True:
                response = get(f"https://{api_url}/collections.json?limit=250&page={collection_index}", 
                             headers={"Content-Type": "application/json"})
                
                if response.status_code == 200:
                    collections = response.json().get('collections', [])
                    if not collections:
                        logging.info(f"Market {market_id} - No more collections to fetch.")
                        break  # No more collections to fetch
                    
                    total_collections.extend(collections)
                    logging.info(f"Market {market_id} - Fetched {len(collections)} collections (page {collection_index})")
                    collection_index += 1
                else:
                    # Fixed: Handle error case properly
                    logging.error(f"Market {market_id} - Failed to fetch collections: {response.status_code} - {response.text}")
                    break
            
            # next loop over all collections and save those with products
            for collection in total_collections:
                if collection.get("products_count", 0) == 0:
                    continue

                collection_id = collection.get('id')
                collection_name = collection.get('handle')

                # Create collection directory
                collection_dir = market_path / f"{collection_name}_{collection_id}"
                collection_dir.mkdir(parents=True, exist_ok=True)
                
                # Save collection metadata
                collection_file = collection_dir / "collection.json"
                with collection_file.open("w") as f:
                    json.dump(collection, f, indent=2)
                
                # Fetch and save products for the collection
                try:
                    product_index = 0  # Fixed: Use different variable name
                    all_products = []  # Fixed: Collect all products first
                    
                    while True:
                        # loop over all products in the collection
                        products_response = get(
                            f"https://{api_url}/collections/{collection_name}/products.json?limit=250&page={product_index}", 
                            headers={"Content-Type": "application/json"}
                        )
                        
                        if products_response.status_code == 200:
                            products_data = products_response.json()
                            products_batch = products_data.get('products', [])
                            
                            if not products_batch:
                                logging.info(f"All products fetched for collection {collection_name}")
                                break  # No more products to fetch
                                
                            all_products.extend(products_batch)
                            product_index += 1
                            
                            logging.info(f"Fetched {len(products_batch)} products (page {product_index}) for collection {collection_name}")
                        else:
                            logging.error(f"Failed to fetch products for collection {collection_id}: {products_response.status_code}")
                            break
                    
                    # Fixed: Save all products at once, not per page
                    if all_products:
                        products_file = collection_dir / "products.json"
                        with products_file.open("w") as f:
                            json.dump({"products": all_products}, f, indent=2)
                        
                        logging.info(f"Saved {len(all_products)} total products for collection {collection_name}")

                except Exception as e:
                    logging.error(f"Exception fetching products for collection {collection_id}: {str(e)}")
                    
        except Exception as e:
            logging.error(f"Market {market_id} - Exception during fetch: {str(e)}")
    
    # Fixed: Add return statement
    return {
        "status": "success", 
        "markets_processed": len(markets),
        "message": f"Successfully processed {len(markets)} markets"
    }

def json_to_parquet(json_file, parquet_file):
     # for each unique product, create or append the parquet file
  
    pass

def stage_shop_data(parquet_file):
      #COPY the raw data into a rw_table in the db
    # transform nd lod into the prices datbase
    pass
