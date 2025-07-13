import os, sys, glob, ijson, functools, requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from pydantic import BaseModel, model_validator
from datetime import datetime
from decimal import Decimal,  getcontext
from typing import List, Any, Optional, Tuple
from psycopg2.extensions import connection
from backend.services.shop_data_fetcher.utils import get_hashed_product_shop_id
from tqdm import tqdm
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Adjust the path if your .env is not in the current working directory

load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))

from backend.database.get_database import get_connection

getcontext().prec = 2

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

class ProductPrice(BaseModel):
    shop_id : int
    product_id : int
    tcgplayer_id : Optional[int] = None  # TCGPlayer product ID, if applicable
    product_shop_id : Optional[str] = None  # Unique identifier for the product in the shop
    price : Decimal
    foil_price : Optional[Decimal]= None
    currency : str = 'AUD'
    price_usd : Optional[Decimal] = None  
    foil_price_usd : Optional[Decimal] = None
    source : Optional[str]=None
    html_body : Optional[str] = None  # HTML body of the product page, if available
    created_at : datetime
    updated_at : datetime

    def batch_tuple(
        self,
        price_field: str,
        usd_field: str,
        is_foil_flag: bool = False,
        default_source: str = "scrapping_service"
    ) -> Tuple[datetime, str, Decimal, str, Decimal, bool, str]:
        base_price = getattr(self, price_field)
        usd_price  = getattr(self, usd_field) or base_price
        source     = self.source or default_source
        return (
            self.updated_at,
            self.product_shop_id,
            base_price,
            self.currency,
            usd_price,
            is_foil_flag,
            source,
        )
    
    @model_validator(mode='after')
    def create_product_shop_id(self):
        if not self.product_shop_id:
            self.product_shop_id = get_hashed_product_shop_id(self.product_id, self.shop_id)
        if self.html_body:
            self.tcgplayer_id = extract_card_tag(self.html_body)
        return self

class BatchProductProces(BaseModel):
    items : List[ProductPrice]

    def __iter__(self):
        return iter(self.items)
    
    def __len__(self):
        # allow: len(batch_proc)
        return len(self.items)
    def __getitem__(self, index):
        # allow: batch_proc[0], slicing, etc.
        return self.items[index]

    def prepare_price_batches(
        self,
        include_foil: bool = False
    ) -> Tuple[
        Tuple[List[datetime], List[str], List[Decimal], List[str], List[Decimal], List[bool], List[str]],
        Optional[Tuple[List[datetime], List[str], List[Decimal], List[str], List[Decimal], List[bool],List[str]]]
    ]:
        """
        Returns a tuple: (normal_batch, foil_batch or None).
        Each batch is a 7-tuple of parallel lists.
        """
        # Build normal batch
        normal = [p.batch_tuple('price', 'price_usd') for p in self.items]
        normal_batch = tuple(map(list, zip(*normal)))

        if not include_foil:
            return normal_batch, None

        # Build foil batch
        foil = [p.batch_tuple('foil_price', 'foil_price_usd',  is_foil_flag=True) for p in self.items if p.foil_price is not None]
        if not foil:
            return normal_batch, None
        foil_batch = tuple(map(list, zip(*foil)))
        return normal_batch, foil_batch


from backend.services.shop_data_fetcher.models.shopify_models import ProductModel

def get_market_id(name : str)-> int:
    from backend.services.shop_data_fetcher.queries import queries

    try:
        pass
    except Exception as e:
        print(f"Error fetching market_id for {name}: {e}")
        return -1

def prepare_product_shop_id_query(validated_batch: BatchProductProces) -> Tuple[
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


def validate_batch(batch: List[Any]) -> BatchProductProces:
    validated_batch = []
    for idx ,item in enumerate(batch):
        try:
            product : ProductPrice = ProductPrice.model_validate(item)
            validated_batch.append(product)
        except Exception as e:
            raise ValueError(f"Validation error in item {item}: {e}")
    return BatchProductProces(items=validated_batch)
             


def bulk_insert_product(batch: Tuple [
    List[datetime], 
    List[int],
    List[Decimal],
    list[str],
    list[Decimal],
    list[str]
], conn: connection):
    try:
        with conn.cursor() as cursor:
            cursor.execute('CALL add_product_batch_arrays(%s, %s, %s, %s, %s)',batch)
            conn.commit()
    except Exception as e:
        print(f"Error during bulk insert: {e}")
        raise


def bulk_insert_prices(batch: Tuple[
    List[datetime],
    List[str],
    List[Decimal],
    List[str],
    List[Decimal],
    List[bool],
    List[str]
      ], conn: connection):
    try:
        with conn.cursor() as cursor:
            cursor.execute('CALL add_price_batch_arrays(%s, %s, %s, %s, %s, %s, %s)', batch)
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error during bulk insert: {e}")
        raise

def find_condition_variant(product: ProductModel, condition: str) -> Optional[float]:
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
        products_model = [ProductModel(**c) for c in items ]
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

def upload_batches_from_stream(path: str, market_id: str, app_id: str, conn: connection, batch_size: int = 1000, product_currency='AUD'):
    for validated_batch in stream_json_file(path, market_id, app_id, batch_size, product_currency):
        #
        prepared_product_input = prepare_product_shop_id_query(validated_batch)
        try:
            bulk_insert_product(prepared_product_input, conn)
        except Exception as e:
            print(f"Error during bulk insert: {e}")
            raise
        normal_batch, foil_batch = validated_batch.prepare_price_batches(include_foil=True)
       # prepared_price_output = prepare_product_price_query((times, ids, prices, currs, usd, srcs))
        try:
            bulk_insert_prices(normal_batch, conn)
            if foil_batch is not None:
                bulk_insert_prices(foil_batch, conn)

        except Exception as e:
            print(f"Error during bulk insert: {e}")
            raise

def upload_all_json_in_directory(directory: str, market_id: str, app_id: str, conn: connection, batch_size: int = 1000, product_currency='AUD'):
    """
    Iterate over all .json files in a directory and upload their contents to the DB in batches.
    Shows a tqdm progress bar for file processing, keeping the bar at the same location.
    """
    json_files = glob.glob(os.path.join(directory, '*.json'))
    with tqdm(json_files, desc="Processing JSON files", dynamic_ncols=True, leave=True) as pbar:
        for path in pbar:
            pbar.set_postfix_str(f"{os.path.basename(path)}")
            try:
                upload_batches_from_stream(path, market_id, app_id, conn, batch_size, product_currency)
            except Exception as e:
                print(f"Error processing {path}: {e}")

def extract_card_tag(body_html):
    soup =BeautifulSoup(body_html, 'html.parser')
    meta = soup.find('div', class_='catalogMetaData')
    if meta and meta.has_attr('data-tcgid'):
        return meta['data-tcgid']
    return None

def insert_card_product_reference(batch: BatchProductProces, conn: connection):
    pass

        

            #bulk_insert(batch)
#-chunk validation
#-batch insert

#extract the prices of product with the product_id

#fecth the market_id from the db

#convert the prices to USD

#create the list of info to insert in the db

#batch inseret

## update the card_product table

if __name__ == "__main__":
    path = r'C:\Users\lorie\OneDrive\Bureau\AutoMana_fastapi\staging\shops\gg_brisbane\products'

    try:
        conn = next(get_connection())
        upload_all_json_in_directory(path, 2, app_id='5b4c2f1fc7b14fe48ffeefd753a566db', conn=conn, batch_size=10, product_currency='AUD')
    except Exception as e:
         print("Error:", e)