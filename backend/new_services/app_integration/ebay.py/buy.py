from httpx import AsyncClient, HTTPStatusError
from backend.modules.ebay.models import auth as auth_model,  errors as errors_model, buy as buy_model

from fastapi import Depends, Query
from typing import List, Optional
from backend.modules.ebay.services import auth as authentificate


async def doBuyRequest( params : dict, headers: dict, enpoint_url: str) -> str:
      try:
         async with AsyncClient() as client:
            response = await client.get(url=enpoint_url, params=params, headers=headers)
            response.raise_for_status()
            return response.text
      except HTTPStatusError as e:
        raise RuntimeError(f"eBay API HTTP error {e.response.status_code}: {e.response.text}")
      except Exception as e:
         raise RuntimeError(f"Failed to contact eBay Trading API: {str(e)}")

async def make_active_listing_search(token : str, 
                                      q: Optional[str] = None,
    category_ids: Optional[List[str]] = Query(default=None),
    charity_ids: Optional[List[str]] = Query(default=None),
    fieldgroups: Optional[List[str]] = Query(default=None),
    filter: Optional[List[str]] = Query(default=None),
    limit: Optional[int] = 50,
    offset: Optional[int] = 0):

    search_params = buy_model.EbayBrowseSearchParams(
        q=q,
        category_ids=category_ids,
        charity_ids=charity_ids,
        fieldgroups=fieldgroups,
        filter=filter,
        limit=limit,
        offset=offset
    )
    api_header = {"Authorization" : f"Bearer {token}",
                  "X-EBAY-C-MARKETPLACE-ID" : "EBAY_AU"}
    query_dict = search_params.to_query_params()
    try:
        response = await doBuyRequest(query_dict, api_header, "https://api.ebay.com/buy/browse/v1/item_summary/search?")
        return response
    except Exception as e:
        return {'Error:' : str(e)}