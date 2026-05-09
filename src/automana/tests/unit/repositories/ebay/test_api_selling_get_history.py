"""Unit tests for EbaySellingRepository.get_history.

Regression guards:
- 728-day window was sending requests eBay rejected with 400, producing zero
  orders silently.  The fix caps the window at 90 days.
- 4xx/5xx responses were silently returned as {} (no "orders" key), causing
  the service layer to yield an empty list instead of raising.
"""
import pytest
import httpx
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository
from automana.core.exceptions.repository_layer_exceptions.ebay_integration import ebay_api_exception


def make_repo(environment="sandbox"):
    repo = EbaySellingRepository.__new__(EbaySellingRepository)
    repo.environment = environment
    repo.timeout = 30
    repo.http2 = True
    repo.base_url = "https://api.sandbox.ebay.com/ws/api.dll"
    repo._client = None
    return repo


def make_json_response(status_code: int, body: dict) -> MagicMock:
    """Build a mock httpx.Response that returns JSON and has a request stub."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = body
    response.text = str(body)
    response.headers = {"content-type": "application/json"}
    # httpx.HTTPStatusError requires a real request object on the response
    response.request = MagicMock(spec=httpx.Request)
    return response


@pytest.mark.asyncio
async def test_get_history_raises_on_400():
    """A 400 from eBay must raise, not silently return {}."""
    repo = make_repo()
    error_body = {"errors": [{"errorId": 1100, "message": "Invalid filter"}]}
    repo.send = AsyncMock(return_value=make_json_response(400, error_body))

    with pytest.raises(Exception):
        await repo.get_history({"token": "tok123"})


@pytest.mark.asyncio
async def test_get_history_raises_on_401():
    """A 401 (bad/expired token) must raise, not return empty orders."""
    repo = make_repo()
    error_body = {"errors": [{"errorId": 1001, "message": "Unauthorized"}]}
    repo.send = AsyncMock(return_value=make_json_response(401, error_body))

    with pytest.raises(Exception):
        await repo.get_history({"token": "tok123"})


@pytest.mark.asyncio
async def test_get_history_raises_on_403():
    """A 403 (missing scope) must raise, not return empty orders."""
    repo = make_repo()
    error_body = {"errors": [{"errorId": 1002, "message": "Forbidden"}]}
    repo.send = AsyncMock(return_value=make_json_response(403, error_body))

    with pytest.raises(Exception):
        await repo.get_history({"token": "tok123"})


@pytest.mark.asyncio
async def test_get_history_returns_parsed_json_on_200():
    """A 200 response with orders is parsed and returned."""
    repo = make_repo()
    orders_body = {"orders": [{"orderId": "ord-1"}], "total": 1}
    repo.send = AsyncMock(return_value=make_json_response(200, orders_body))

    result = await repo.get_history({"token": "tok123"})
    assert result.get("orders") == [{"orderId": "ord-1"}]
    assert result.get("total") == 1


@pytest.mark.asyncio
async def test_get_history_date_range_is_within_90_days():
    """The creationdate filter must not exceed the 90-day eBay limit."""
    repo = make_repo()
    orders_body = {"orders": [], "total": 0}
    repo.send = AsyncMock(return_value=make_json_response(200, orders_body))

    fixed_now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    with patch(
        "automana.core.repositories.app_integration.ebay.ApiSelling_repository.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        await repo.get_history({"token": "tok123"})

    call_params = repo.send.call_args[1]["params"]
    filter_str = call_params["filter"]
    # Extract start date from creationdate:[START..END]
    start_str = filter_str.split("[")[1].split("..")[0]
    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    delta_days = (fixed_now - start_dt).days
    assert delta_days <= 90, f"Date range {delta_days} days exceeds 90-day eBay limit"


@pytest.mark.asyncio
async def test_get_history_raises_on_missing_token():
    repo = make_repo()
    with pytest.raises(ValueError, match="Token is required"):
        await repo.get_history({})


@pytest.mark.asyncio
async def test_get_history_uses_sandbox_url_for_sandbox_env():
    repo = make_repo(environment="sandbox")
    orders_body = {"orders": [], "total": 0}
    repo.send = AsyncMock(return_value=make_json_response(200, orders_body))

    await repo.get_history({"token": "tok123"})
    call_url = repo.send.call_args[0][1]
    assert "sandbox.ebay.com" in call_url


@pytest.mark.asyncio
async def test_get_history_uses_production_url_for_production_env():
    repo = make_repo(environment="production")
    orders_body = {"orders": [], "total": 0}
    repo.send = AsyncMock(return_value=make_json_response(200, orders_body))

    await repo.get_history({"token": "tok123"})
    call_url = repo.send.call_args[0][1]
    assert "sandbox" not in call_url
    assert "api.ebay.com" in call_url


@pytest.mark.asyncio
async def test_get_history_passes_limit_and_offset():
    repo = make_repo()
    orders_body = {"orders": [], "total": 0}
    repo.send = AsyncMock(return_value=make_json_response(200, orders_body))

    await repo.get_history({"token": "tok123", "limit": 25, "offset": 50})
    call_params = repo.send.call_args[1]["params"]
    assert call_params["limit"] == 25
    assert call_params["offset"] == 50
