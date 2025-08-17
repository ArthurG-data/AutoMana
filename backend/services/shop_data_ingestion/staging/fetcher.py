
from urllib.parse import  urlunsplit
from backend.services.shop_data_ingestion.models.error_models import InternalServiceError
from datetime import datetime
import os, csv, json, httpx, time
from tqdm import tqdm
from backend.schemas.external_marketplace.shopify.shopify_theme import CollectionModel, ProductModel, ResponseModel
from backend.schemas.external_marketplace.shopify.utils import LogStatus, Status
from backend.dependancies import get_internal_settings


def create_url_query(scheme, netloc, path, query=None, fragment=None)->str:
    return urlunsplit((scheme, netloc, path, query, fragment))

def log_csv_event(log_update : LogStatus, log_path = get_internal_settings().get('STAGING_PATH') + '/logs/shop_data_fetcher.txt'):

    log_row = [log_update.timestamp, log_update.shop, log_update.collection, log_update.page,  log_update.filename or "", log_update.status]
    
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    file_exists = os.path.isfile(log_path)
    with open(log_path, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(['timestamp', 'shop', 'collection', 'page', 'file_path', 'status'])
        writer.writerow(log_row)

def get_timestamp(date_format : str ="%Y-%m-%dT%H-%M-%S")->datetime:
    return datetime.utcnow().strftime(date_format)

def log_event(timestamp, shop, collection, page, filename, status):
    log_event = LogStatus(timestamp=timestamp, shop=shop, collection=collection, page=page, filename=filename, status=Status.STAGED)
    log_csv_event(log_event)
    
def save_query_response_data(response_model : ResponseModel, filename):
    serialized = {
        "items": [item.model_dump(mode="json") for item in response_model.items],
        "count": response_model.count
    }
    with open(filename, 'w', encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, default=str)
          
def get_collections_query(query)->ResponseModel:
    r = httpx.get(query)
    json_response = r.json()
    collections = json_response.get('collections', [])
    collections = [CollectionModel(**c) for c in collections]
    return ResponseModel(items = collections)

def get_products_query(query)->ResponseModel:
    r = httpx.get(query)
    json_response = r.json()
    products = json_response.get('products', [])
    products_model = [ProductModel(**c) for c in products]
    return ResponseModel(items = products_model)
    
def save_collection_for_staging(shop,shop_url, page_num=1):
    current_page = page_num
    while True: 
        timestamp : datetime = get_timestamp()
        query : str = create_url_query('https',shop_url, 'collections.json',f'limit=250&page={current_page}')
        print(query)
        try:
            response_model : ResponseModel= get_collections_query(query)
        except Exception as e:
            raise InternalServiceError("Failed to fetch collection data", context={"query": query, "error": str(e)})
            
        filename = os.path.join(get_internal_settings().get('STAGING_PATH'), 'shops',shop,  'collections',f"{timestamp}_page_{current_page}.json")
        
        try:
            save_query_response_data(response_model, filename)
            log_event(timestamp=timestamp, shop=shop,collection='collections' , page=current_page, filename=filename, status=Status.STAGED)
        except Exception as e:
            raise InternalServiceError("Failed to save collection date", context={"query": query, "error": str(e)})
        if response_model.count < 250:
            break
        current_page +=1

def is_collection_product_type(shop_url, collection, product_type = "MTG Single")->bool:
    #get the first item, latter get more and look for any of the target vendor
    #refractor the request latter
    query : str = create_url_query('https',shop_url, f'collections/{collection}/products.json',f'limit=1')
    try:
        product : ResponseModel = get_products_query(query)
        if product.count == 0:
            return False
    except Exception as e:
            raise InternalServiceError("Failed to get product for verification of product type", context={"query": query, "error": str(e)})
    return product.items[0].product_type == product_type
                             
def save_products_for_staging(shop,shop_url, collection, page_num=1):
    current_page=page_num
    while True:
        timestamp = get_timestamp()
        filename = os.path.join(get_internal_settings().get('STAGING_PATH'), shop,'products',f"{timestamp}_{collection}_page_{current_page}.json")
        query = create_url_query('https',shop_url, f'collections/{collection}/products.json',f'limit=250&page={current_page}')
        try:
            products : ResponseModel = get_products_query(query)
        except Exception as e:
            print(e)
            raise InternalServiceError("Failed to fetch", context={"query": query, "error": str(e)})
        
        filename : str = os.path.join(get_internal_settings().get('STAGING_PATH'), 'shops',shop,  'products',f"{timestamp}_{collection}_page_{current_page}.json")
        try:
            save_query_response_data(products, filename)
            log_event(timestamp=timestamp, shop=shop,collection=collection , page=current_page, filename=filename, status=Status.STAGED)
        except Exception as e:
            raise InternalServiceError("Failed to save products data", context={"query": query, "error": str(e)})
            
        if products.count < 250:
            break
        current_page +=1
        print(current_page)
    
def log_collection_type(shop_url :str ,shop : str, collection: str, log_path):
    
    is_mtg =  is_collection_product_type(shop_url, collection)
    log_row = [get_timestamp(), shop, collection,  is_mtg]
    
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    file_exists = os.path.isfile(log_path)
    with open(log_path, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(['timestamp', 'shop', 'collection', 'is_mtg'])
        writer.writerow(log_row)

def explore_collections(shop, shop_url, collection_file_path):
    with open(collection_file_path, mode='r', encoding='utf-8') as f:
        data = json.load(f)  # Expecting a list of dicts like [{"shop": ..., "collection": ...}, ...]
        data_items = data.get("items", "")
        for entry in tqdm(data_items, desc=f"Processing collections for {shop}", unit="collection"):
            collection = entry.get("handle")
            if collection:
                log_collection_type(shop_url, shop, collection,get_internal_settings().get('STAGING_PATH') + '/logs/collection_log.txt')
        
def clean_collection_import_lists(collection_file_path):
    handles_count = {}
    suffixes = ['singles']
    with open(collection_file_path) as csv_file:
        reader =csv.reader(csv_file)
        headers = next(reader, None)
        rows = list(reader)
        for entry in tqdm(rows, total=len(rows), desc='Cleaning the collection log-> looking for singles', unit="Entry"):
            if entry[2].endswith('singles') and entry[3] == 'True':
                count = handles_count.get(entry[2],  0)
                handles_count[entry[2]] = count +1
    with open(collection_file_path, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['shop', 'collection', 'is_mtg', 'added_on', 'updated_on'])
        for k in handles_count:
            log_row = ['gg_brisbane', k, True,get_timestamp(),get_timestamp() ]
            writer.writerow(log_row)
 
            
excluded_list = ['modern-legal-mtg-singles', 'standard-legal-mtg-singles']
                
def download_mtg_related_collection(shop, shop_url, complete_log_class):
    with open(complete_log_class, mode='r', encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader, None)
        for row in reader:
            if row[2] in excluded_list :
                continue
            try:
                save_products_for_staging(shop, shop_url, row[1])
            except Exception as e:
                raise e
            finally:
                time.sleep(2)
    pass