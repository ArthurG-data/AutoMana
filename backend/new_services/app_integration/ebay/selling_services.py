from typing import Any
import logging

logger = logging.getLogger(__name__)

async def handle_selling_request(
                                  auth_repository,
                                  selling_repository,
                                  action :str,
                                  payload: dict[str, Any],
                                  **kwargs):
   try:
       logger.info("fetching app_code...")
       app_code = payload.get("app_code")
       if not app_code:
          logger.error("App code is missing in the payload")
          raise ValueError("App code is required in the payload")
       token = await auth_repository.get_valid_access_token(user_id = payload['user_id'], app_code=app_code)
       if not token:
           logger.error("Token not found")
           raise ValueError("Token not found")
       logger.info(f"Handling selling request with action: {action}.")
       payload["token"] = token
       if action == "create":
          return await selling_repository.create_listing(payload)
       if action == "update":
          return await selling_repository.update_listing(payload)
       if action == "delete":
          return await selling_repository.delete_listing(payload)
       if action == "get":
          return await selling_repository.get_listing(payload)
       if action == "get_history":
          return await selling_repository.get_history(payload)
       if action == "get_active":
          return await selling_repository.get_active(payload)
       else:
          raise ValueError(f"Unknown action: {action}")
   except Exception as e:
        logger.error(f"Error handling selling request: {str(e)}")
        raise

    
"""
async def obtain_all_active_listings(token : str)->listings_model.ActiveListingResponse:#- listings_model.ActiveListingResponse
   api_header = auth_model.HeaderApi(site_id = "15", iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   all_items = []
   page_number = 1
   while True:
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

"""