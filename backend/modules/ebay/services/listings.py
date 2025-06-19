from httpx import AsyncClient, HTTPStatusError
from backend.modules.ebay.models import auth as auth_model, listings as listings_model, errors as errors_model
from backend.modules.ebay.config import EBAY_TRADING_API_URL as trading_endpoint
from backend.modules.ebay.services import requests
from backend.modules.ebay.utils import listings

import xml.etree.ElementTree as ET

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

async def obtain_item(token : str, item_id : str)->listings_model.ItemModel:
   api_header = auth_model.HeaderApi(site_id = "15",call_name='GetItem', iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   test_xml = requests.create_xml_body_get_item(item_id)
   response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   return await listings.parse_single_item(response_xml)


async def obtain_all_active_listings(token : str)->listings_model.ActiveListingResponse:#- listings_model.ActiveListingResponse
   api_header = auth_model.HeaderApi(site_id = "15", iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   all_items = []
   page_number = 1
   while True:
      print(page_number)
      test_xml = requests.create_xml_body('GetMyeBaySellingRequest',limit=100,offset=page_number)
      response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
      active_listings  = await listings.parse_listings_response(response_xml)
      if len(active_listings) == 0:
         return listings_model.ActiveListingResponse(items=all_items)
      all_items.extend(active_listings)
      page_number += 1

async def add_or_verify_post_new_item(card: listings_model.ItemModel, token: str, verify : bool=True):
   class_name_input = "AddItem"
   if verify:
      class_name_input = "VerifyAddItem"
   api_header = auth_model.HeaderApi(site_id = "15",call_name = class_name_input, iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   test_xml = requests.generate_add_item_request_xml(card)
   response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   return listings.parse_verify_add_item_response(response_xml)
   
async def update_listing(updatedItem : listings_model.ItemModel, token: str):
   api_header = auth_model.HeaderApi(site_id = "15",call_name = 'ReviseItem', iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   test_xml = requests.generate_revise_item_request_xml(updatedItem)
   response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   return response_xml

async def delete_listing(item_id :str, token : str, reason = None):
   api_header = auth_model.HeaderApi(site_id = "15",call_name = 'EndItemRequest', iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   xml = requests.generate_end_item_request_xml(item_id, reason=None)
   response_xml = await doPostTradingRequest(xml, headers, trading_endpoint)
   return response_xml