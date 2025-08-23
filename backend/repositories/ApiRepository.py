# backend/repositories/ApiRepository.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx
from backend.exceptions.repository_layer_exceptions.ebay_integration import ebay_api_exception
from backend.schemas.app_integration.ebay.trading_api import HeaderApi

class ApiRepository(ABC):
    """Base class for repositories that interact with external APIs"""

    def __init__(self, base_url: str = None, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the repository"""
        pass
    
    async def _make_get_request(
        self, 
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[HeaderApi]=None,
        xml : Optional[str]=None
    ) -> Dict[str, Any]:
        """Make a GET request to the API"""
        #robably will need to be fixed, request type should be in it
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url=url, **params,data=xml if xml else None, headers=headers.model_dump(by_alias=True) if headers else None)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            raise self._handle_http_error(e)
        except httpx.RequestError as e:
            raise ebay_api_exception.EbayBuyApiConnectionError(f"Failed to connect to API: {str(e)}")
        except Exception as e:
            raise ebay_api_exception.EbayBaseRepositoryError(f"Unexpected error in API call: {str(e)}")
    
    async def _make_post_request(
        self, 
        url: str, 
        headers: Optional[HeaderApi]=None,
        data: Optional[Dict[str, Any]]=None,
        xml : Optional[str]=None,
        trading_headers: Optional[HeaderApi]=None
    ) -> Dict[str, Any]:
        """Make a POST request to the API"""
        print("test:", url, headers, data, xml)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if data is not None:
                    response = await client.post(
                        url=url,
                        data=data,
                        headers=headers if headers else {}
                    )
                elif xml is not None:
                    response = await client.post(
                        url=url,
                        data=xml,
                        headers=trading_headers.model_dump(by_alias=True) if trading_headers else {}
                    )
                else:
                    response = await client.post(
                        url=url,
                        headers=headers or {}
                    )
                response.raise_for_status()
                return response.json()
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
                f"Authentication failed: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        elif status_code == 403:
            return ebay_api_exception.EbayBuyApiForbiddenError(
                f"Permission denied: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        elif status_code == 404:
            return ebay_api_exception.EbayBuyApiNotFoundError(
                f"Resource not found: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        elif status_code == 405:  # ✅ Add 405 handler
            return ebay_api_exception.EbayBaseRepositoryError(
                f"Method not allowed (405): {error.response.text}. Check if you're making requests to authorization URLs.",
                status_code=status_code,
                error_data=error_data
        )
        elif status_code == 429:
            return ebay_api_exception.EbayBuyApiRateLimitError(
                f"Rate limit exceeded: {error.response.text}",
                status_code=status_code,
                error_data=error_data
            )
        else:
            return ebay_api_exception.EbayBaseRepositoryError(
                f"HTTP error {status_code}: {error.response.text}",
                status_code=status_code,
                error_data=error_data
        )
    def _parse_xml_response(self, xml_response: str) -> Dict[str, Any]:
        """Parse XML response to dictionary"""
        # Implementation needed - you could use xmltodict or ElementTree
        # This is a placeholder
        import xmltodict
        return xmltodict.parse(xml_response)

    def _create_ebay_headers(self, token: str, marketplace_id: str) -> Dict[str, str]:
        """Create standard eBay API headers"""
        return {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
            "Content-Type": "application/json"
        }