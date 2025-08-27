# backend/repositories/ApiRepository.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx
import logging
from pydantic import BaseModel
from backend.exceptions.repository_layer_exceptions.ebay_integration import ebay_api_exception
from backend.schemas.app_integration.ebay.trading_api import HeaderApi
import xmltodict
import xml.etree.ElementTree as ET 

logger = logging.getLogger(__name__)

class ApiRepository(ABC):
    """Base class for repositories that interact with external APIs"""

    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        self.environment = environment.lower()
        self.timeout = timeout
        self.base_url = self._get_base_url(self.environment)
        if self.environment not in ["sandbox", "production"]:
            raise ValueError(f"Invalid environment: {self.environment}. Must be 'sandbox' or 'production'.")
        logger.info(f"API Repository initialized for {self.environment} environment.")
    #maybe a dict mapping tith env and url as well instead of hardcoding
    
    @abstractmethod
    def _get_base_url(self, environment: str) -> str:
        """Return the base URL for the given environment"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the repository"""
        pass

    @property
    def is_production(self) -> bool:
        """Return True if the environment is production"""
        return self.environment == "production"
    
    @property
    def is_sandbox(self) -> bool:
        """Return True if the environment is sandbox"""
        return self.environment == "sandbox"

    def get_full_url(self, endpoint: str) -> str:
        if endpoint.startswith("http"):
            return endpoint
        endpoint = endpoint.lstrip("/")
        base = self.base_url.rstrip("/")
        return f"{base}/{endpoint}"

    async def _make_get_request(
        self, 
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[dict]=None,
        xml : Optional[str]=None
    ) -> Dict[str, Any]:
        """Make a GET request to the API"""
        #robably will need to be fixed, request type should be in it
        try:

            full_url = self.get_full_url(url)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url=full_url
                                            , params=params
                                            , headers=headers if headers else None)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "application/json" in content_type:
                    return response.json()
                elif "xml" in content_type:
                    return self._parse_xml_response(response.text)
                else:
                    return response.text

        except httpx.HTTPStatusError as e:
            raise self._handle_http_error(e)
        except httpx.RequestError as e:
            raise ebay_api_exception.EbayBuyApiConnectionError(message=f"Failed to connect to API: {str(e)}")
        except Exception as e:
            raise ebay_api_exception.EbayBaseRepositoryError(message=f"Unexpected error in API call: {str(e)}")

    async def _make_post_request(
        self, 
        url: str, 
        headers: Optional[dict]=None,
        data: Optional[Dict[str, Any]]=None,
        xml : Optional[str]=None,
        trading_headers: Optional[dict]=None
    ) -> Dict[str, Any]:
        """Make a POST request to the API"""

        try:
            full_url = self.get_full_url(url)

            logger.debug(f"Making POST request to {full_url}.")
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if data is not None:

                    headers["Content-Type"] = "application/json"
                    response = await client.post(
                        url=full_url,
                        data=data,
                        headers=headers if headers else {}
                    )
                elif xml is not None:
                    request_headers = trading_headers.model_dump(by_alias=True) if trading_headers else {}
                    request_headers["Content-Type"] = "text/xml"

                    response = await client.post(
                        url=full_url,
                        data=xml,
                        headers=request_headers
                    )
                else:
                    response = await client.post(
                        url=full_url,
                        content=xml,
                        headers=headers or {}
                    )
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "application/json" in content_type:
                    return response.json()
                elif "xml" in content_type:
                    return self._parse_xml_response(response.text)
                else:
                    return response.text
        except httpx.HTTPStatusError as e:
            raise self._handle_http_error(e)
        except httpx.RequestError as e:
            raise ebay_api_exception.EbayBuyApiConnectionError(message="Failed to connect to API", status_code=404, error_data=str(e))
        except Exception as e:
            raise ebay_api_exception.EbayBaseRepositoryError(message="Failed to connect to API", status_code=404, error_data=str(e))

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> ebay_api_exception.EbayBaseRepositoryError:
        """Handle HTTP errors and convert to appropriate repository exceptions"""
        status_code = error.response.status_code
        error_data = {"response_text": error.response.text}
        
        if status_code == 401:
            return ebay_api_exception.EbayBuyApiUnauthorizedError(
                message=f"Authentication failed: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        elif status_code == 403:
            return ebay_api_exception.EbayBuyApiForbiddenError(
                message=f"Permission denied: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        elif status_code == 404:
            return ebay_api_exception.EbayBuyApiNotFoundError(
                message=f"Resource not found: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        elif status_code == 405:  # ✅ Add 405 handler
            return ebay_api_exception.EbayBaseRepositoryError(
                message=f"Method not allowed (405): {error.response.text}. Check if you're making requests to authorization URLs.",
                status_code=status_code,
                error_data=error_data
        )
        elif status_code == 429:
            return ebay_api_exception.EbayBuyApiRateLimitError(
                message=f"Rate limit exceeded: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        else:
            return ebay_api_exception.EbayBaseRepositoryError(
                message=f"HTTP error {status_code}: {error.response.text}",
                status_code=status_code,
                error_data=error_data
        )
    def _parse_xml_response(self, xml_response: str) -> Dict[str, Any]:
        """Parse XML response to dictionary"""
        # Implementation needed - you could use xmltodict or ElementTree
        # This is a placeholder
        import xmltodict
        return xmltodict.parse(xml_response)

    def _create_ebay_headers(self
                             , token: str
                             , marketplace_id: Optional[str] = "15"
                             , call_name : Optional[str]=None
                             , compatibility_level: Optional[str] = "1421"
                             , type: Optional[str] = 'xml') -> Dict[str, str]:
        """Create standard eBay API headers"""
        headers = {
            "X-EBAY-API-IAF-TOKEN": token,#"Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
            "Content-Type": f"{'application/json' if type == 'json' else 'text/xml'}"
        }
        if call_name:
            headers["X-EBAY-C-API-CALL-NAME"] = call_name
        if compatibility_level:
            headers["X-EBAY-API-COMPATIBILITY-LEVEL"] = compatibility_level
        return headers

    def _create_auth_header(self, token: str) -> Dict[str, str]:
        """Create authorization header for eBay API requests"""
        return {
            "Authorization": f"Bearer {token}"
        }