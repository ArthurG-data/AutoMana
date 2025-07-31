import os, sys, glob, ijson, functools, requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))


from datetime import datetime
from decimal import Decimal,  getcontext
from typing import List, Any, Optional, Tuple
from psycopg2.extensions import connection

from tqdm import tqdm
from dotenv import load_dotenv
from backend.services_old.shop_data_ingestion.db import QueryExecutor, ErrorHandler
from backend.services_old.shop_data_ingestion.models import shopify_theme

# Adjust the path if your .env is not in the current working directory

load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))

from backend.database.get_database import get_connection

getcontext().prec = 2

syncPsycorgHandler = ErrorHandler.Psycopg2ExceptionHandler()
psycorgSyncHandler = QueryExecutor.SyncQueryExecutor(get_connection(), syncPsycorgHandler)

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

def get_market_id(name : str)-> int:
    from backend.services_old.shop_data_ingestion.queries import queries

    try:
        pass
    except Exception as e:
        print(f"Error fetching market_id for {name}: {e}")
        return -1

def prepare_product_shop_id_query(validated_batch: shopify_theme.BatchProductProces) -> Tuple[
    list[str],
    list[str],
    list[int],
    list[datetime],
    list[datetime]
]:
    p_product_shop_ids : List[str] = []
    p_product_ids : List[str] = []
    p_market_ids : List[int] = []
    p_created_at : List[datetime] = []
    p_updated_at : List[datetime] = []
    for product in validated_batch:
        p_product_shop_ids.append(product.product_shop_id)
        p_product_ids.append(str(product.product_id))
        p_market_ids.append(product.shop_id)
        p_created_at.append(product.created_at)
        p_updated_at.append(product.updated_at) 
    
    return (p_product_shop_ids, p_product_ids, p_market_ids, p_created_at, p_updated_at  ) 


def validate_batch(batch: List[Any]) -> shopify_theme.BatchProductProces:
    validated_batch = []
    for idx ,item in enumerate(batch):
        try:
            product : shopify_theme.ProductPrice = shopify_theme.ProductPrice.model_validate(item)
            validated_batch.append(product)
        except Exception as e:
            raise ValueError(f"Validation error in item {item}: {e}")
    return shopify_theme.BatchProductProces(items=validated_batch)
             
def bulk_insert_product(batch: Tuple [
    List[datetime], 
    List[int],
    List[Decimal],
    list[str],
    list[Decimal],
    list[str]
], queryExecutor: QueryExecutor.QueryExecutor):
    query = 'CALL add_product_batch_arrays(%s, %s, %s, %s, %s)'
    queryExecutor.execute_command(query, batch)
 

def bulk_insert_prices(batch: Tuple[
    List[datetime],
    List[str],
    List[Decimal],
    List[str],
    List[Decimal],
    List[bool],
    List[str]
      ], queryExecutor: QueryExecutor.QueryExecutor):
    
    query = """
    CALL add_price_batch_arrays(%s, %s, %s, %s, %s, %s, %s)
    """
    queryExecutor.execute_command(query,batch )
  

def find_condition_variant(product: shopify_theme.ProductModel, condition: str) -> Optional[float]:
    """
    Find the price of a variant with the specified condition in the product.
    Returns None if no such variant exists.
    """
    for v in product.variants:
        if condition.lower() in v.title.lower():
            return v.price
    return None


def stream_json_file(path: str, market_id: str, app_id: str, batch_size: int = 1000, product_currency='AUD'):
    """
    Stream and yield validated batches of ProductPrice from a JSON file.
    Does not perform DB upload; just yields the validated batch for further processing.
    """
    with open(path, 'r', encoding='utf-8') as file:
        batch = []
        items = ijson.items(file, 'items.item')
        products_model = [shopify_theme.ProductModel(**c) for c in items ]
        for obj in products_model: 
            date = obj.updated_at.date().isoformat() 
            exange_rate = fetch_fx_rate(product_currency, 'USD', date, app_id)
            batch.append(
                {
                    'product_id': obj.id,
                    'shop_id': market_id,
                    'price': find_condition_variant(obj, "Near Mint"),
                    'price_usd': Decimal(find_condition_variant(obj, "Near Mint")) * Decimal(exange_rate),
                    'foil_price':find_condition_variant(obj, "Near Mint Foil"),
                    'foil_price_usd': Decimal(find_condition_variant(obj, "Near Mint Foil")) * Decimal(exange_rate) if find_condition_variant(obj, "Near Mint Foil") else None,
                    'html_body': obj.body_html,
                    'currency': product_currency,
                    'created_at': obj.created_at,
                    'updated_at': obj.updated_at,
                    'source': 'test_source'
                }
            )
            if len(batch) >= batch_size:
                validated_batch = validate_batch(batch)
                yield validated_batch
                batch.clear()
        if batch:
            validated_batch = validate_batch(batch)
            yield validated_batch

# New function to upload batches yielded by the stream

def upload_batches_from_stream(path: str, market_id: str, app_id: str, queryExecutor: QueryExecutor.QueryExecutor, batch_size: int = 1000, product_currency='AUD'):
    for validated_batch in stream_json_file(path, market_id, app_id, batch_size, product_currency):
        #
        """
        prepared_product_input = prepare_product_shop_id_query(validated_batch)
        try:
            bulk_insert_product(prepared_product_input, conn)
        except Exception as e:
            print(f"Error during bulk insert: {e}")
            raise
        normal_batch, foil_batch = validated_batch.prepare_price_batches(include_foil=True)
     
        try:
            bulk_insert_prices(normal_batch, conn)
            if foil_batch is not None:
                bulk_insert_prices(foil_batch, conn)

        except Exception as e:
            print(f"Error during bulk insert: {e}")
            raise
        """
       
        insert_card_product_reference(validated_batch, queryExecutor)
       

def upload_all_json_in_directory(directory: str, market_id: str, app_id: str, queryExecutor : QueryExecutor.SyncQueryExecutor, batch_size: int = 1000, product_currency='AUD'):
    """
    Iterate over all .json files in a directory and upload their contents to the DB in batches.
    Shows a tqdm progress bar for file processing, keeping the bar at the same location.
    """
    json_files = glob.glob(os.path.join(directory, '*.json'))
    with tqdm(json_files, desc="Processing JSON files", dynamic_ncols=True, leave=True) as pbar:
        for path in pbar:
            pbar.set_postfix_str(f"{os.path.basename(path)}")
            try:
                upload_batches_from_stream(path, market_id, app_id, queryExecutor, batch_size, product_currency)
            except Exception as e:
                print(f"Error processing {path}: {e}")

def insert_card_product_reference(batch: shopify_theme.BatchProductProces,queryExecutor : QueryExecutor.QueryExecutor):
    query = """
    CALL add_card_product_ref_batch(%s,%s,%s,%s);
    """
    queryExecutor.execute_command(query,  batch.prepare_prodcut_card_batches())
    
def insert_theme(values : shopify_theme.InsertTheme , queryExecutor : QueryExecutor.SyncQueryExecutor):
    query = """
    INSERT INTO theme_ref (code, name)
    VALUES (%s, %s)
    ON CONFLICT (code) DO NOTHING;
    """
    queryExecutor.execute_command(query, (values.code, values.name))
   
   
def insert_collection(values : shopify_theme.InsertCollection, queryExecutor : QueryExecutor.SyncQueryExecutor):
    query = """
    INSERT INTO collection_handles (market_id, name)
    VALUES (SELECT market_id FROM market_ref WHERE name = %s), %s
    ON CONFLICT (name) DO NOTHING;
    """
    queryExecutor.execute_command(query,(values.market_id, values.name) )
   
def insert_collection_theme(values : shopify_theme.InsertCollectionTheme, queryExecutor : QueryExecutor.SyncQueryExecutor):
    query = """
    INSERT INTO handles_theme (handle_id, theme_id)
    SELECT
      ch.handle_id,
      tr.theme_id
    FROM
      collection_handles AS ch
      JOIN theme_ref          AS tr ON TRUE
    WHERE
      ch.name = %s
      AND tr.code = %s
    ON CONFLICT (handle_id, theme_id) DO NOTHING;
    """
    queryExecutor.execute_command(query, (values.collection_name, values.theme_code))
   
if __name__ == "__main__":
    path = r'C:\Users\lorie\OneDrive\Bureau\AutoMana_fastapi\staging\shops\gg_brisbane\products'
    conn = next(get_connection())
    print(type(conn))
    
    syncPsycorgHandler = ErrorHandler.Psycopg2ExceptionHandler()
    psycorgSyncHandler = QueryExecutor.SyncQueryExecutor(conn, syncPsycorgHandler)
    upload_all_json_in_directory(path, 2, app_id='5b4c2f1fc7b14fe48ffeefd753a566db', queryExecutor=psycorgSyncHandler, batch_size=1000, product_currency='AUD')
