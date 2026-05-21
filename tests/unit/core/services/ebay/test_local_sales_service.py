import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from automana.core.services.app_integration.ebay.local_sales_service import (
    list_local_sales,
)


def _repo(rows, total):
    r = MagicMock()
    r.list_local_sales = AsyncMock(return_value=(rows, total))
    return r


@pytest.mark.asyncio
async def test_returns_items_and_pagination():
    row = {
        "order_id": "ord-1",
        "local_status": "sold",
        "buyer_username": "bob",
        "sold_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "currency": "AUD",
        "total_price_cents": 1000,
        "line_items": [],
    }
    result = await list_local_sales(
        ebay_sales_repository=_repo([row], 1),
        app_code="my-app",
        limit=25,
        offset=0,
    )
    assert result["total"] == 1
    assert result["has_more"] is False
    assert result["items"][0]["order_id"] == "ord-1"


@pytest.mark.asyncio
async def test_has_more_true_when_more_rows_exist():
    rows = [{"order_id": f"ord-{i}"} for i in range(25)]
    result = await list_local_sales(
        ebay_sales_repository=_repo(rows, 100),
        app_code="my-app",
        limit=25,
        offset=0,
    )
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_has_more_false_at_last_page():
    rows = [{"order_id": "ord-1"}]
    result = await list_local_sales(
        ebay_sales_repository=_repo(rows, 26),
        app_code="my-app",
        limit=25,
        offset=25,
    )
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_empty_result():
    result = await list_local_sales(
        ebay_sales_repository=_repo([], 0),
        app_code="my-app",
        limit=25,
        offset=0,
    )
    assert result == {"items": [], "total": 0, "has_more": False}


@pytest.mark.asyncio
async def test_passes_app_code_and_pagination_to_repo():
    repo = _repo([], 0)
    await list_local_sales(
        ebay_sales_repository=repo,
        app_code="app-X",
        limit=10,
        offset=30,
    )
    repo.list_local_sales.assert_called_once_with(
        app_code="app-X", limit=10, offset=30
    )
