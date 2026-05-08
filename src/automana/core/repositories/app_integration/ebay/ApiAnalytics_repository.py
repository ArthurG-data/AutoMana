import logging
from typing import Optional

from automana.core.models.ebay.auth import AuthHeader
from automana.core.repositories.app_integration.ebay.EbayApiRepository import EbayApiClient

logger = logging.getLogger(__name__)

_ANALYTICS_PATH = "/developer/analytics/v1_beta/rate_limit/"
_TOKEN_PATH = "/identity/v1/oauth2/token"
_APP_SCOPE = "https://api.ebay.com/oauth/api_scope"


class EbayAnalyticsAPIRepository(EbayApiClient):
    URL_MAPPING = {
        "sandbox": "https://api.sandbox.ebay.com",
        "production": "https://api.ebay.com",
    }

    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        self.environment = environment.lower()
        super().__init__(environment=environment, timeout=timeout)

    @property
    def name(self):
        return "EbayAnalyticsAPIRepository"

    def _get_base_url(self) -> str:
        url = self.URL_MAPPING.get(self.environment)
        if not url:
            raise ValueError(f"No URL for eBay environment: {self.environment!r}")
        return url

    async def _get_app_token(self, app_id: str, secret: str) -> str:
        """Fetch a client-credentials application token (not user-scoped)."""
        headers = AuthHeader(app_id=app_id, secret=secret).to_header()
        data = {"grant_type": "client_credentials", "scope": _APP_SCOPE}
        response = await self.send(
            "POST", f"{self.base_url}{_TOKEN_PATH}", headers=headers, data=data
        )
        parsed = self._parse_response(response)
        return parsed["access_token"]

    async def get_rate_limits(self, app_id: str, secret: str) -> list[dict]:
        """Return rate limit usage for all APIs under this eBay app.

        Each entry has: api_name, resource, limit, remaining, reset, time_window_seconds.
        """
        token = await self._get_app_token(app_id, secret)
        response = await self.send(
            "GET",
            f"{self.base_url}{_ANALYTICS_PATH}",
            headers={
                **self.auth_header(token),
                "Content-Type": "application/json",
            },
        )
        parsed = self._parse_response(response)
        results = []
        for api in parsed.get("rateLimits", []):
            api_name = api.get("apiName", "")
            for resource in api.get("resources", []):
                resource_name = resource.get("name", "")
                for rate in resource.get("rates", []):
                    results.append(
                        {
                            "api_name": api_name,
                            "resource": resource_name,
                            "limit": rate.get("limit"),
                            "remaining": rate.get("remaining"),
                            "reset": rate.get("reset"),
                            "time_window_seconds": rate.get("timeWindow"),
                        }
                    )
        logger.info(
            "ebay_rate_limits_fetched",
            extra={"environment": self.environment, "resource_count": len(results)},
        )
        return results
