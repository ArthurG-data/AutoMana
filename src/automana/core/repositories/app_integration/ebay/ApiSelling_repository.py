from automana.core.repositories.app_integration.ebay.EbayApiRepository import EbayApiClient
from automana.core.services.app_integration.ebay.xml_utils import generate_add_fixed_price_item_request_xml, generate_end_item_request_xml, generate_get_item_request_xml, generate_revise_item_request_xml, generate_get_my_ebay_selling_request_xml, generate_upload_site_hosted_pictures_request_xml
import logging
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
import httpx

logger = logging.getLogger(__name__)


class EbaySellingRepository(EbayApiClient):

    URL_MAPPING = {
        "sandbox": "https://api.sandbox.ebay.com/ws/api.dll",
        "production": "https://api.ebay.com/ws/api.dll"
    }

    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        # Must be set before super().__init__() because the base constructor calls _get_base_url().
        self.environment = environment.lower()
        super().__init__(timeout=timeout)

    @property
    def name(self):
        return "EbaySellingAPIRepository"

    def _get_base_url(self) -> str:
        url = self.URL_MAPPING.get(self.environment)
        if not url:
            raise ValueError(f"No URL configured for environment: {self.environment}")
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
        headers = self.trading_headers(
            token,
            marketplace_id=payload.get("marketplace_id", "15"),
            call_name="AddFixedPriceItem",
        )
        headers["Content-Type"] = "text/xml"
        response = await self.send("POST", "", content=xml_request, headers=headers)
        return self._parse_response(response)

    async def update_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing eBay listing"""
        logger.info("Updating an eBay listing")
        item = payload.get("item")
        if not item:
            raise ValueError("Payload must include 'item' data")
        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")
        xml_request = generate_revise_item_request_xml(item)
        headers = self.trading_headers(
            token,
            marketplace_id=payload.get("marketplace_id", "15"),
            call_name="ReviseItem",
        )
        headers["Content-Type"] = "text/xml"
        response = await self.send("POST", "", content=xml_request, headers=headers)
        return self._parse_response(response)

    async def delete_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an eBay listing"""
        logger.info("Deleting an eBay listing")
        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")
        item_id = payload.get("item_id")
        if not item_id:
            raise ValueError("Item ID is required")
        call_name = "VerifyEndItem" if payload.get("verify") else "EndItem"
        xml_request = generate_end_item_request_xml(item_id, payload.get("ending_reason", "NotAvailable"))
        headers = self.trading_headers(
            token,
            marketplace_id=payload.get("marketplace_id", "15"),
            call_name=call_name,
        )
        headers["Content-Type"] = "text/xml"
        response = await self.send("POST", "", content=xml_request, headers=headers)
        return self._parse_response(response)

    async def get_active(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get the active listings of an eBay user.

        Returns the raw xmltodict response. The service layer is responsible
        for extracting items and `PaginationResult` (`TotalNumberOfEntries`,
        `TotalNumberOfPages`) — repositories should not make schema-shaping
        decisions.
        """
        logger.info("Getting the active listings of an eBay user")
        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")
        limit = payload.get("limit", 10)
        # eBay's GetMyeBaySelling uses 1-indexed PageNumber; the service layer
        # translates offset→page before calling this method.
        offset = payload.get("offset", 0)
        xml_request = generate_get_my_ebay_selling_request_xml(
            entries_per_page=limit, page_number=offset
        )
        headers = self.trading_headers(
            token,
            marketplace_id=payload.get("marketplace_id", "15"),
            call_name="GetMyeBaySelling",
        )
        headers["Content-Type"] = "text/xml"
        response = await self.send("POST", "", content=xml_request, headers=headers)
        return self._parse_response(response)

    async def get_listing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get a single eBay listing by `item_id`.

        Uses the Trading API ``GetItem`` call. Schema-shaping (xmltodict →
        `ItemModel`) is deferred to the service layer.
        """
        logger.info("Getting a single eBay listing")
        token = payload.get("token")
        item_id = payload.get("item_id")
        if not token:
            raise ValueError("Token is required")
        if not item_id:
            raise ValueError("Item ID is required")
        xml_request = generate_get_item_request_xml(item_id)
        headers = self.trading_headers(
            token,
            marketplace_id=payload.get("marketplace_id", "15"),
            call_name="GetItem",
        )
        headers["Content-Type"] = "text/xml"
        response = await self.send("POST", "", content=xml_request, headers=headers)
        return self._parse_response(response)

    async def get_history(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get eBay order history via the Fulfillment REST API (last 2 years)."""
        logger.info("Getting the history of an eBay listing")
        token = payload.get("token")
        if not token:
            raise ValueError("Token is required")

        url = (
            "https://api.sandbox.ebay.com/sell/fulfillment/v1/order"
            if self.environment == "sandbox"
            else "https://api.ebay.com/sell/fulfillment/v1/order"
        )

        now = datetime.now(timezone.utc)
        two_years_ago = now - timedelta(days=728)
        params = {
            "filter": f"creationdate:[{two_years_ago.strftime('%Y-%m-%dT%H:%M:%SZ')}..{now.strftime('%Y-%m-%dT%H:%M:%SZ')}]",
            "limit": payload.get("limit", 10),
            "offset": payload.get("offset", 0),
        }

        headers = self.auth_header(token)
        response = await self.send("GET", url, headers=headers, params=params)
        return self._parse_response(response)

    async def upload_picture(
        self,
        token: str,
        file_bytes: bytes,
        content_type: str,
        marketplace_id: str = "15",
    ) -> str:
        xml_payload = generate_upload_site_hosted_pictures_request_xml()
        headers = self.trading_headers(
            token,
            marketplace_id=marketplace_id,
            call_name="UploadSiteHostedPictures",
        )
        files = {
            "XML Payload": ("payload.xml", xml_payload.encode("utf-8"), "text/xml;charset=utf-8"),
            "image": ("image", file_bytes, content_type),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self._get_base_url(), files=files, headers=headers)
        response.raise_for_status()

        import xmltodict
        parsed = xmltodict.parse(response.text)
        resp_data = parsed.get("UploadSiteHostedPicturesResponse", {})
        ack = resp_data.get("Ack", "")
        if ack not in ("Success", "Warning"):
            errors = resp_data.get("Errors", {})
            raise ValueError(f"eBay upload rejected: {errors}")
        url = resp_data.get("SiteHostedPictureDetails", {}).get("FullURL")
        if not url:
            raise ValueError("eBay returned no picture URL in upload response")
        return url
