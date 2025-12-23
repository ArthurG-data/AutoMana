from backend.repositories.ApiRepository import ApiRepository
from backend.utils.app_integration.ebay.xml_utils import generate_add_fixed_price_item_request_xml, generate_end_item_request_xml, generate_get_item_request_xml, generate_revise_item_request_xml, generate_get_my_ebay_selling_request_xml
import logging
from typing import Dict, Any
import xml.etree.ElementTree as ET 
from datetime import datetime, timedelta
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EbaySellingRepository(ApiRepository):

    URL_MAPPING = {
        "sandbox": "https://api.sandbox.ebay.com/ws/api.dll",
        "production": "https://api.ebay.com/ws/api.dll"
    }




    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        super().__init__(environment=environment, timeout=timeout)
    
    @property
    def name(self):
        return "EbaySellingAPIRepository"
    
    def _get_base_url(self, environment):
        url = self.URL_MAPPING.get(environment)
        if not url:
            raise ValueError(f"No URL configured for environment: {environment}")
        return url

  
    async def create_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new eBay listing"""
        logger.info("Creating a new eBay listing")

        item = payload.get("item")
        if not item:
            raise ValueError("Payload must include 'item' data")
        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")
        xml_request = generate_add_fixed_price_item_request_xml(item)
        logger.debug(f"Generated XML Request: {xml_request}")
        headers = self._create_ebay_headers(token=token,
                                             marketplace_id=payload.get("marketplace_id", '15'),
                                             call_name="AddFixedPriceItemRequest")

        return await self._make_post_request("", xml=xml_request, headers=headers)

    async def update_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing eBay listing"""
        logger.info("Updating an eBay listing")
        class_name_input = "ReviseItem"
        item = payload.get("item")
        if not item:
            raise ValueError("Payload must include 'item' data")
        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")
        xml_request = generate_revise_item_request_xml(item)
        headers = self._create_ebay_headers(token=token,
                                             marketplace_id=payload["marketplace_id"],
                                             call_name=class_name_input)
        return await self._make_post_request("", xml=xml_request, headers=headers)

    async def delete_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an eBay listing"""
        logger.info("Deleting an eBay listing")
        class_name_input = "EndItemRequest"
        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")
        item_id = payload.get("item_id")
        if not item_id:
            raise ValueError("Item ID is required")
        if payload.get("verify"):
            logger.info("Verification is enabled for this deletion")
            class_name_input = "VerifyEndItem"
        xml_request = generate_end_item_request_xml(item_id, payload.get("ending_reason", "NotAvailable"))
        headers = self._create_ebay_headers(token=token,
                                             marketplace_id=payload["marketplace_id"],
                                             call_name=class_name_input)
        return await self._make_post_request("", xml=xml_request, headers=headers)

    async def get_active(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get the active listings of an eBay user"""
        logger.info("Getting the active listings of an eBay user")
        token = payload.get("token")
        limit = payload.get("limit", 10)
        offset = payload.get("offset", 0)
        if not token:
            raise ValueError("Token is required")
        xml_request = generate_get_my_ebay_selling_request_xml(entries_per_page=limit
                                                               , page_number=offset)
    
        headers = self._create_ebay_headers(token=token,
                                             marketplace_id=payload.get("marketplace_id", "15"),
                                             call_name="GetMyeBaySelling")
        logger.debug(f"Generated XML Request: {xml_request}")
        return await self._make_post_request("", xml=xml_request, headers=headers)
    


    async def get_history(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get the history of an eBay listing"""
        "improve in future"
        logger.info("Getting the history of an eBay listing")

        url = f"https://api{'.sandbox' if self.environment == 'sandbox' else ''}.ebay.com/sell/fulfillment/v1/order"

        now = datetime.utcnow()

# 2 years ago
        two_years_ago = now - timedelta(days=728)
        start = two_years_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "filter": f"creationdate:[{start}..{end}]",
            "limit": payload.get("limit", 10),
            "offset": payload.get("offset", 0)
        }

        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")
        headers = self._create_auth_header(token)
        return await self._make_get_request(url, headers=headers, params=params)
