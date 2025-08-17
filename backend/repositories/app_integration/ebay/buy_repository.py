from backend.repositories.ApiRepository import ApiRepository
from backend.exceptions.repository_layer_exceptions.ebay_integration import ebay_api_exception
from typing import Dict, Any, Optional, List
from httpx import AsyncClient, HTTPStatusError
from backend.schemas.external_marketplace.ebay import EbayXmlBuilder
from backend.schemas.app_integration.ebay.listings import ItemModel
from backend.schemas.app_integration.ebay.trading_api import HeaderApi

class EbayBuyRepository(ApiRepository):
    """Repository for eBay Buy API operations"""

    API_URL = "https://api.ebay.com/buy/browse/v1"  # Base URL for eBay Buy API, use a factory later to create the repos, and have the url in a db
    def __init__(self, base_url: str = API_URL, timeout: int = 30):
        super().__init__(base_url, timeout) 
        self.API_URL = base_url  # Allow overriding the base URL if needed

    @property
    def name(self) -> str:
        return "EbayBuyRepository"
    
    async def get_item(self, item_id: str, token: str) -> Optional[Dict[str, Any]]:
        """Get item details by ID"""
        xml_request = EbayXmlBuilder.create_get_item_request(item_id)
        header = HeaderApi(site_id="15", call_name="GetItem", iaf_token=token)
        return await self._make_post_request("GetItem", xml_request, header)
    async def add_item(self, item: ItemModel, token: str) -> Dict[str, Any]:
        """Add an item to eBay"""
        xml_request = EbayXmlBuilder.create_add_item_request(item)
        header = HeaderApi(site_id="15", call_name="AddItem", iaf_token=token)
        return await self._make_post_request("AddItem", xml_request, header)

    async def revise_item(self, item: ItemModel, token: str) -> Dict[str, Any]:
        """Update an existing item on eBay"""
        if not item.ItemID:
            raise ValueError("ItemID is required to revise a listing")
        
        xml_request = EbayXmlBuilder.create_revise_item_request(item)
        header = HeaderApi(site_id="15", call_name="ReviseItem", iaf_token=token)
        return await self._make_post_request("ReviseItem", xml_request, header)

    async def end_item(self, item_id: str, reason: str, token: str) -> Dict[str, Any]:
        """End an item listing on eBay"""
        xml_request = EbayXmlBuilder.create_end_item_request(item_id, reason)
        header = HeaderApi(site_id="15", call_name="EndItem", iaf_token=token)
        return await self._make_post_request("EndItem", xml_request, header)
