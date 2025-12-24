import xml
from fastapi import requests
import logging
from httpx import AsyncClient, HTTPStatusError
from typing import Optional, List
from backend.schemas.app_integration.ebay import listings as listings_model
from backend.schemas.app_integration.ebay import auth as auth_model
from backend.repositories.app_integration.ebay.ApiBrowse_repository  import EbayBrowseAPIRepository
from backend.exceptions.service_layer_exceptions.app_integration.ebay import app_exception
from backend.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

@ServiceRegistry.register(
    path="integrations.ebay.search",
    db_repositories=[],
    api_repositories=["ebay_browse_api"]
)
async def search_items(
    search_repository: EbayBrowseAPIRepository,
    token: str,
    q: Optional[str] = None,
    gtin: Optional[str] = None,
    charity_ids: Optional[List[str]] = None,
    fieldgroups: Optional[List[str]] = None,
    compatibility_filter: Optional[str] = None,
    auto_correct: Optional[str] = None,
    category_ids: Optional[List[str]] = None,
    filter: Optional[List[str]] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    aspect_filter: Optional[str] = None,
    epid: Optional[str] = None,
    **kwargs) -> listings_model.SearchResult:
    """
    Search eBay items using Browse API
    
    Args:
        q: Search keywords (max 100 chars)
        gtin: Global Trade Item Number (UPC, EAN, ISBN)
        charity_ids: List of charity IDs (max 20)
        fieldgroups: Response field groups
        compatibility_filter: Product compatibility filter
        auto_correct: Enable auto correction
        category_ids: Category ID filters
        filter: Field filters
        sort: Sort criteria
        limit: Number of results (1-200, default 50)
        offset: Pagination offset (0-9999, default 0)
        aspect_filter: Item aspect filters
        epid: eBay Product ID
    """

    try:
    # Build query parameters
      params = {}

      # Basic search parameters
      if q:
            params["q"] = q[:100]  # Truncate to 100 chars
      if gtin:
            params["gtin"] = gtin
      if epid:
            params["epid"] = epid

      # Array parameters (convert to comma-separated strings)
      if charity_ids:
            params["charity_ids"] = ",".join(charity_ids[:20])  # Max 20
      if fieldgroups:
            params["fieldgroups"] = ",".join(fieldgroups)
      if category_ids:
            params["category_ids"] = ",".join(category_ids)
      if filter:
            params["filter"] = ",".join(filter)

      # Single value parameters
      if compatibility_filter:
            params["compatibility_filter"] = compatibility_filter
      if auto_correct:
            params["auto_correct"] = auto_correct
      if sort:
            params["sort"] = sort
      if aspect_filter:
            params["aspect_filter"] = aspect_filter

      # Pagination
      params["limit"] = min(max(1, limit), 200)  # Clamp between 1-200
      params["offset"] = min(max(0, offset), 9999)  # Clamp between 0-9999

      # Validate offset is multiple of limit (if not 0)
      if params["offset"] > 0 and params["offset"] % params["limit"] != 0:
            raise ValueError("Offset must be zero or a multiple of limit")
      #needs to be an auth header
      headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
      }
      response_json = await search_repository.search_items(params, headers=headers)
      search_result = listings_model.SearchResult.model_validate(response_json)
      return search_result
    except Exception as e:
      logger.error(f"Error occurred while searching eBay items: {str(e)}")
      raise

   #response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   #return listings.parse_search_response(response_xml)

"""
async def obtain_item(token : str, item_id : str)->listings_model.ItemModel:
   #first check if the listing is in the cache
   cached_xml = redis_ebay.get_cached_ebay_item(item_id)
   if not cached_xml:
      api_header = auth_model.HeaderApi(site_id = "15",call_name='GetItem', iaf_token = token)
      headers = api_header.model_dump(by_alias=True)
      response_xml = requests.create_xml_body_get_item(item_id)
      cached_xml = await doPostTradingRequest(response_xml, headers, trading_endpoint)
      
      redis_ebay.cache_ebay_item(item_id, cached_xml)
   parsed_item = await listings.parse_single_item(cached_xml)
   #cache the item
   return parsed_item

"""