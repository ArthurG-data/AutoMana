from httpx import AsyncClient, HTTPStatusError
from backend.modules.ebay.models import auth as auth_model, listings as listings_model, errors as errors_model
from backend.modules.ebay.config import EBAY_TRADING_API_URL as trading_endpoint
from backend.modules.ebay.services import requests
from backend.modules.ebay.utils import listings


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

async def obtain_all_active_listings(token : str)-> listings_model.ActiveListingResponse:
   test_xml = requests.create_xml_body('GetMyeBaySellingRequest')
   api_header = auth_model.HeaderApi(site_id = "0", iaf_token = token)
   headers = api_header.model_dump(by_alias=True)
   try:
      response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
      active_listings  = listings.parse_active_listings(response_xml)
      if active_listings:
         return listings_model.ActiveListingResponse(items=active_listings)
      else:
         return listings_model.ActiveListingResponse(items=[])
   except Exception as e:
       raise errors_model.ExternalServiceError(f"eBay API call failed: {e}")
  
