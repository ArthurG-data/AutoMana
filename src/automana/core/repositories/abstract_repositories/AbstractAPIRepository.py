# backend/repositories/ApiRepository.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
from urllib.parse import urljoin
import httpx, logging,  xmltodict
from httpx import Response
from automana.core.exceptions.repository_layer_exceptions import api_errors
from automana.core.exceptions.repository_layer_exceptions.base_repository_exception import RepositoryError

logger = logging.getLogger(__name__)

ParsedResponse = Union[Dict[str, Any], str, bytes]
    
class BaseApiClient(ABC):
    """
    Generic HTTP client base for external integrations.
    Integration-specific concerns (exception mapping, auth headers, base URLs) belong in subclasses.
    """

    def __init__(self, timeout: float = 30.0, http2: bool = True, **kwargs):
        self.timeout = timeout
        self.base_url = self._get_base_url()
        self.http2 = http2
        self._client : Optional[httpx.AsyncClient] = None
        logger.info("%s initialized base_url=%s", self.__class__.__name__, self.base_url)

    async def __aenter__(self):
        self._client = httpx.AsyncClient(http2=self.http2, timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        # If user didn't use "async with", still work (but not ideal)
        if self._client is None:
            self._client = httpx.AsyncClient(http2=self.http2, timeout=self.timeout)
        return self._client
    
    def default_headers(self) -> Dict[str, str]:
        """Override in subclasses if they need default headers."""
        return {}

    @abstractmethod
    def _get_base_url(self) -> str:
        """Return the base URL for the given environment"""
        pass

    @abstractmethod
    def default_headers(self) -> Dict[str, str]:
        """Return default headers for the API requests"""
        return {}
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the repository"""
        pass

    def get_full_url(self, endpoint: str) -> str:
        from urllib.parse import urljoin
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return urljoin(self.base_url.rstrip("/") + "/", endpoint.lstrip("/"))
    
    def _parse_response(self, response: httpx.Response) -> ParsedResponse:
        content_type = (response.headers.get("content-type") or "").lower()
        logger.info(f"Parsing response with content-type: {content_type}")
        if "application/json" in content_type:
            return response.json()

        if "xml" in content_type or response.text.strip().startswith("<"):
            parsed = xmltodict.parse(response.text)
            return self._clean_xml_dict(parsed)
        if any(ext in content_type for ext in ["xz", "gzip", "zip", "octet-stream"]):
            return response.content
        return response.text
    
    def _clean_xml_dict(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                nk = k.lstrip("@").lstrip("#")
                cleaned[nk] = self._clean_xml_dict(v)
            return cleaned
        if isinstance(obj, list):
            return [self._clean_xml_dict(x) for x in obj]
        return obj
    
    def map_http_error(self, error: httpx.HTTPStatusError) -> RepositoryError:
        status = error.response.status_code
        body = error.response.text
        error_data = {"response_text": body}

        if status == 401:
            return api_errors.ExternalApiUnauthorizedError(
                message=f"Unauthorized calling {self.name}: {body}",
                error_code="EXTERNAL_API_UNAUTHORIZED",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )
        if status == 403:
            return api_errors.ExternalApiForbiddenError(
                message=f"Forbidden calling {self.name}: {body}",
                error_code="EXTERNAL_API_FORBIDDEN",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )
        if status == 404:
            return api_errors.ExternalApiNotFoundError(
                message=f"Not found calling {self.name}: {body}",
                error_code="EXTERNAL_API_NOT_FOUND",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )
        if status == 405:
            return api_errors.ExternalApiMethodNotAllowedError(
                message=f"Method not allowed calling {self.name}: {body}",
                error_code="EXTERNAL_API_METHOD_NOT_ALLOWED",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )
        if status == 429:
            return api_errors.ExternalApiRateLimitError(
                message=f"Rate limit calling {self.name}: {body}",
                error_code="EXTERNAL_API_RATE_LIMIT",
                status_code=status,
                error_data=error_data,
                source_exception=error,
            )

        return api_errors.ExternalApiHttpError(
            message=f"HTTP {status} calling {self.name}: {body}",
            error_code="EXTERNAL_API_HTTP_ERROR",
            status_code=status,
            error_data=error_data,
            source_exception=error,
        )

    async def send(
        self,
        method: str,
        endpoint: str,
        *,
        params=None,
        headers=None,
        json=None,
        data=None,
        timeout=None
    ) -> httpx.Response:
    
        url = self.get_full_url(endpoint)

        merged_headers = dict(self.default_headers())
        if headers:
            merged_headers.update(headers)
        client = self._get_client()
        
        logger.info(f"Making {method.upper()} request to {url}")
        try:
            return await client.request(method.upper(), url, params=params, headers=merged_headers, json=json, data=data, timeout=timeout)
        except httpx.HTTPStatusError as e:
            raise self.map_http_error(e)
        except httpx.RequestError as e:
            raise api_errors.ExternalApiConnectionError(
                message=f"Failed to connect to {self.name}: {e}",
                error_code="EXTERNAL_API_CONNECTION_ERROR",
                status_code=None,
                error_data={"url": url},
                source_exception=e,
            )
        except RepositoryError:
            raise
        except Exception as e:
            raise api_errors.ExternalApiError(
                message=f"Unexpected error calling {self.name}: {e}",
                error_code="EXTERNAL_API_UNEXPECTED_ERROR",
                error_data={"url": url},
                source_exception=e,
            )

