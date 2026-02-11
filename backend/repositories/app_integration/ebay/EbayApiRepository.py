# backend/repositories/ApiRepository.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx
import logging
from backend.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient
from backend.exceptions.repository_layer_exceptions.ebay_integration import ebay_api_exception
from backend.exceptions.repository_layer_exceptions.base_repository_exception import RepositoryError

logger = logging.getLogger(__name__)

class EbayApiClient(BaseApiClient):
    """Base class for repositories that interact with external APIs"""
    
    def _get_base_url(self, environment: str) -> str:
        
        mapping = {
            "sandbox": "https://api.sandbox.ebay.com",
            "production": "https://api.ebay.com",
        }
        env = environment.lower()
        if env not in mapping:
            raise ValueError(f"Invalid eBay environment: {environment}")
        return mapping[env]
    def map_http_error(self, error: httpx.HTTPStatusError) -> RepositoryError:
        status = error.response.status_code
        body = error.response.text
        error_data = {"response_text": body}

        if status == 401:
            return ebay_api_exception.EbayBuyApiUnauthorizedError(
                message=f"Authentication failed: {body}",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )
        if status == 403:
            return ebay_api_exception.EbayBuyApiForbiddenError(
                message=f"Permission denied: {body}",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )
        if status == 404:
            return ebay_api_exception.EbayBuyApiNotFoundError(
                message=f"Resource not found: {body}",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )
        if status == 429:
            return ebay_api_exception.EbayBuyApiRateLimitError(
                message=f"Rate limit exceeded: {body}",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )

        return ebay_api_exception.EbayBaseRepositoryError(
            message=f"HTTP error {status}: {body}",
            status_code=status,
            error_data=error_data,
            source_exception=error,
        )
    
    def auth_header(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def trading_headers(
        self,
        token: str,
        *,
        marketplace_id: str = "15",
        call_name: Optional[str] = None,
        compatibility_level: str = "1421",
    ) -> Dict[str, str]:
        return {
            "X-EBAY-API-SITEID": marketplace_id,
            "X-EBAY-API-COMPATIBILITY-LEVEL": compatibility_level,
            "X-EBAY-API-CALL-NAME": call_name or "",
            "X-EBAY-API-IAF-TOKEN": token,
        }

