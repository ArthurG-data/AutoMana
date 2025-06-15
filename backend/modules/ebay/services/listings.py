from httpx import AsyncClient, HTTPStatusError
from backend.modules.ebay.models import auth as auth_model, listings as listings_model, errors as errors_model
from backend.modules.ebay.config import EBAY_TRADING_API_URL as trading_endpoint
from backend.modules.ebay.services import requests
from backend.modules.ebay.utils import listings
from typing import Optional
import xmltodict


async def doPostTradingRequest( xml_body : str, headers: auth_model.HeaderApi, enpoint_url: str) -> str:
      try:
         async with AsyncClient() as client:
            response = await client.post(enpoint_url, data=xml_body, headers=headers)
            response.raise_for_status()
            return response.text
      except HTTPStatusError as e:
        raise RuntimeError(f"eBay API HTTP error {e.response.status_code}: {e.response.text}")
      except Exception as e:
         raise RuntimeError(f"Failed to contact eBay Trading API: {str(e)}")

import xml.etree.ElementTree as ET
def parse_get_item_response(xml_text: str) -> dict:
    ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
    root = ET.fromstring(xml_text)
    item_elem = root.find("e:Item", ns)
    if item_elem is None:
        raise ValueError("No <Item> found in response.")

    def get_text(path):
        el = item_elem.find(path, ns)
        return el.text if el is not None else None

    def get_price(path):
        el = item_elem.find(path, ns)
        return float(el.text) if el is not None else None

    return {
        "item_id": get_text("e:ItemID"),
        "title": get_text("e:Title"),
        "start_price": get_price("e:StartPrice"),
        "current_price": get_price("e:SellingStatus/e:CurrentPrice"),
        "currency": item_elem.find("e:SellingStatus/e:CurrentPrice", ns).attrib.get("currencyID"),
        "start_time": get_text("e:ListingDetails/e:StartTime"),
        "end_time": get_text("e:ListingDetails/e:EndTime"),
        "view_url": get_text("e:ListingDetails/e:ViewItemURL"),
        "image_url": get_text("e:PictureDetails/e:PictureURL"),
        "quantity": int(get_text("e:Quantity") or 0),
        "quantity_sold": int(get_text("e:SellingStatus/e:QuantitySold") or 0),
        "condition": get_text("e:ConditionDisplayName"),
        "location": get_text("e:Location"),
        "postal_code": get_text("e:PostalCode"),
    }

def flatten_for_pydantic(data):
    if isinstance(data, dict):
        # Case: currency-wrapped float value
        if "@currencyID" in data and "#text" in data:
            return float(data["#text"])
        
      


        # Recursively flatten nested dict
        return {k: flatten_for_pydantic(v) for k, v in data.items()}

    elif isinstance(data, list):
        return [flatten_for_pydantic(item) for item in data]

    else:
        return data
async def obtain_item(token : str, item_id : str):
   api_header = auth_model.HeaderApi(site_id = "15",call_name='GetItem', iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   test_xml = requests.create_xml_body_get_item(item_id)
   response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   parsed = xmltodict.parse(response_xml)
   item_data = parsed.get("GetItemResponse", {}).get("Item", {})
   flattened = flatten_for_pydantic(item_data)
   return listings_model.ItemModel(**flattened)

   

async def obtain_all_active_listings(token : str)-> listings_model.ActiveListingResponse:
   api_header = auth_model.HeaderApi(site_id = "0", iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   all_items = []
   page_number = 1
   while True:
      test_xml = requests.create_xml_body('GetMyeBaySellingRequest',limit=100,offset=page_number)
      response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
      active_listings  = listings.parse_active_listings(response_xml)
      if len(active_listings) == 0:
         return listings_model.ActiveListingResponse(items=all_items)
      all_items.extend(active_listings)
      page_number += 1

async def add_or_verify_post_new_item(card: listings_model.CardListing, token: str, verify : bool=True):
   class_name_input = "AddItem"
   if verify:
      class_name_input = "VerifyAddItem"
   api_header = auth_model.HeaderApi(site_id = "15",class_name = class_name_input, iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   test_xml = requests.build_card_listing_xml(card, token, verify=verify)
   response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   return listings.parse_verify_add_item_response(response_xml)
   
async def update_listing(updatedItem : listings_model.ListingUpdate, token: str):
   api_header = auth_model.HeaderApi(site_id = "15",class_name = 'ReviseItem', iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   test_xml = requests.build_update(updatedItem.item_id, updatedItem.price, updatedItem.pictures)
   response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   return response_xml
