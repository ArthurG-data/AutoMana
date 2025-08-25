from backend.repositories.ApiRepository import ApiRepository
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EbaySellingRepository(ApiRepository):

    URL_MAPPING = {
        "SANDBOX": "https://api.sandbox.ebay.com/sell/inventory/v1",
        "PRODUCTION": "https://api.ebay.com/sell/inventory/v1"
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
        class_name_input = "AddItem"
        if payload.get("verify"):
            logger.info("Verification is enabled for this listing")
            class_name_input = "VerifyAddItem"
        headers = self._create_ebay_headers(token=payload["token"],
                                             marketplace_id=payload["marketplace_id"],
                                             call_name=class_name_input)
        return await self._make_post_request("/inventory_item", data=payload, headers=headers)

    async def update_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing eBay listing"""
        logger.info("Updating an eBay listing")
        class_name_input = "ReviseItem"
        if payload.get("verify"):
            logger.info("Verification is enabled for this listing")
            class_name_input = "VerifyReviseItem"
        headers = self._create_ebay_headers(token=payload["token"],
                                             marketplace_id=payload["marketplace_id"],
                                             call_name=class_name_input)
        
    async def delete_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an eBay listing"""
        logger.info("Deleting an eBay listing")
        class_name_input = "EndItemRequest"
        if payload.get("verify"):
            logger.info("Verification is enabled for this deletion")
            class_name_input = "VerifyEndItem"
        headers = self._create_ebay_headers(token=payload["token"],
                                             marketplace_id=payload["marketplace_id"],
                                             call_name=class_name_input)
        
    """
   headers = api_header.model_dump(by_alias=True)
   test_xml = requests.generate_add_item_request_xml(card)
   response_xml = await doPostTradingRequest(test_xml, headers, trading_endpoint)
   return listings.parse_verify_add_item_response(response_xml)"""