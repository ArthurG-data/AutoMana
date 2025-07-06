## insert the prices of products in the db
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
# create the model of the output from the json files
from pydantic import BaseModel, model_validator
from datetime import datetime
from decimal import Decimal,  getcontext
from typing import List, Any, Optional, Tuple
from psycopg2.extensions import connection
from backend.services.shop_data_fetcher.utils import get_hashed_product_shop_id
import ijson
import functools
import requests

from backend.dependancies import get_internal_settings

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
    product_shop_id : Optional[str] = None  # Unique identifier for the product in the shop
    price : Decimal
    currency : str = 'AUD'
    price_usd : Optional[Decimal] = None  
    source : Optional[str]=None
    date : datetime

    @model_validator(mode='after')
    def create_product_shop_id(self):
        if not self.product_shop_id:
            self.product_shop_id = get_hashed_product_shop_id(self.product_id, self.shop_id)
        return self
    
def get_market_id(name : str)-> int:
    from backend.services.shop_data_fetcher.queries import queries

    try:
        pass
    except Exception as e:
        print(f"Error fetching market_id for {name}: {e}")
        return -1
    
def validate_batch(batch: List[Any])-> Tuple [
    List[datetime], 
    List[int],
    List[Decimal],
    list[str],
    list[Decimal],
    list[str]
]:
    p_times:            List[datetime] = []
    p_product_shop_ids: List[int]      = []
    p_prices:           List[Decimal]  = []
    p_currencies:      List[str]      = []
    p_usd_prices:      List[Decimal]  = []
    p_sources:          List[str]      = []

    for idx ,item in enumerate(batch):
      
        try:
            product : ProductPrice = ProductPrice.model_validate(item)
        except Exception as e:
            raise ValueError(f"Validation error in item {item}: {e}")
        p_times.append(product.date)
        p_product_shop_ids.append(product.product_shop_id)
        p_prices.append(product.price)
        p_currencies.append(product.currency)
        p_usd_prices.append(product.price_usd if product.price_usd else product.price)
        p_sources.append(product.source)

    return p_times, p_product_shop_ids, p_prices, p_currencies, p_usd_prices,p_sources
        
def bulk_insert(batch: Tuple [
    List[datetime], 
    List[int],
    List[Decimal],
    list[str],
    list[Decimal],
    list[str]
], conn: connection):
    try:
        with conn.cursor() as cursor:
            cursor.callproc('add_price_batch_arrays',batch)
            conn.commit()
    except Exception as e:
        print(f"Error during bulk insert: {e}")
        raise
            
def stream_json_file(path:str, market_id : str , app_id: str,batch_size :int = 1000, product_currency = 'AUD') :
    with open(path, 'r', encoding='utf-8') as file:
        batch = []
        items = ijson.items(file, 'items.item')
        for obj in items:
            date = obj['updated_at'][:10]
            exange_rate = fetch_fx_rate(product_currency, 'USD', date, app_id)
            batch.append(
                {
                    'product_id': obj['id'],
                    'shop_id': market_id,
                    'price': obj['variants'][0]['price'],#hopes to grab the near mint price
                    'price_usd': Decimal(obj['variants'][0]['price']) * Decimal(exange_rate),
                    'currency': product_currency,
                    'date': obj['updated_at'], 
                    'source': 'test_source'  # Replace with actual source if available
                }
            )
            if len(batch) >= batch_size:
                validated_batch = validate_batch(batch)
                print(validated_batch[0])
                return
                #bulk_insert(batch)
                #yield?
                batch.clear()
        # leftover
        if batch:
            validated_batch = validate_batch(batch)
            print(validated_batch)
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
    path = r'C:\Users\lorie\OneDrive\Bureau\AutoMana_fastapi\staging\shops\gg_brisbane\products\2025-06-29T05-28-59_final-fantasy-singles_page_1.json'
    try:
        result = stream_json_file(path, 1, batch_size=1000, product_currency='AUD', app_id='5b4c2f1fc7b14fe48ffeefd753a566db')
     
        # print("validate_batch result:", result)
    except Exception as e:
         print("Error:", e)