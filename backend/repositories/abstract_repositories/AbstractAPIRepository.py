# backend/repositories/ApiRepository.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union, Callable
import httpx, logging,  xmltodict
from backend.exceptions.repository_layer_exceptions import api_errors
from backend.exceptions.repository_layer_exceptions.base_repository_exception import RepositoryError

logger = logging.getLogger(__name__)

ParsedResponse = Union[Dict[str, Any], str, bytes]
    
class BaseApiClient(ABC):
    """
    Generic HTTP client base for external integrations.
    Integration-specific concerns (exception mapping, auth headers, base URLs) belong in subclasses.
    """

    def __init__(self, timeout: int = 30, **kwargs):
        self.timeout = timeout
        self.base_url = self._get_base_url()
        logger.info("%s initialized base_url=%s", self.__class__.__name__, self.base_url)

    
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
        if endpoint.startswith("http"):
            return endpoint
        endpoint = endpoint.lstrip("/")
        return f"{self.base_url.rstrip('/')}/{endpoint}"
    
    def _parse_response(self, response: httpx.Response) -> ParsedResponse:
        content_type = (response.headers.get("content-type") or "").lower()

        if "application/json" in content_type:
            return response.json()

        if "xml" in content_type or response.text.strip().startswith("<"):
            parsed = xmltodict.parse(response.text)
            return self._clean_xml_dict(parsed)

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

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        response_parser: Optional[Callable[[httpx.Response], ParsedResponse]] = None,
    ) -> ParsedResponse:
        url = self.get_full_url(endpoint)
        print(f"Making {method.upper()} request to {url} with params={params} and json={json}")
        hdrs = dict(headers or {})  # avoid None + accidental mutation
        t = timeout or self.timeout
        try:
            async with httpx.AsyncClient(timeout=t) as client:
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    headers=hdrs,
                    json=json,     # ✅ correct for JSON payload
                    data=data,     # ✅ raw payload or form-encoded if dict
                )
                resp.raise_for_status()
                return (response_parser or self._parse_response)(resp)

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
    async def send(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
    ) -> httpx.Response:
        url = self.get_full_url(endpoint)
        hdrs = dict(self.default_headers())
        if headers:
            hdrs.update(headers)

        t = timeout or self.timeout

        try:
            if self.client is None:
                async with httpx.AsyncClient(timeout=t) as c:
                    print(f"Making {method.upper()} request to {url} with params={params} and json={json}")
                    return await c.request(method.upper(), url, params=params, headers=hdrs, json=json, data=data)
            print(f"Making {method.upper()} request to {url} with params={params} and json={json}")
            return await self.client.request(method.upper(), url, params=params, headers=hdrs, json=json, data=data)

        except httpx.RequestError as e:
            raise api_errors.ExternalApiConnectionError(
                message=f"Failed to connect to {self.name}: {e}",
                error_code="EXTERNAL_API_CONNECTION_ERROR",
                error_data={"url": url},
                source_exception=e,
            ) from e

