import pytest
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository


def make_repo():
    conn = MagicMock()
    repo = EbayAppRepository.__new__(EbayAppRepository)
    repo.connection = conn
    repo.executor = None
    return repo


@pytest.mark.asyncio
async def test_get_order_statuses_returns_dict_keyed_by_order_id(monkeypatch):
    repo = make_repo()
    fake_rows = [
        {"order_id": "ord-1", "local_status": "sent", "tracking_number": None,
         "carrier_code": None, "shipped_at": None},
    ]
    repo.execute_query = AsyncMock(return_value=fake_rows)

    result = await repo.get_order_statuses(app_code="myapp", order_ids=["ord-1", "ord-2"])

    assert result == {
        "ord-1": {"order_id": "ord-1", "local_status": "sent", "tracking_number": None,
                  "carrier_code": None, "shipped_at": None}
    }
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_order_statuses_empty_returns_empty_dict(monkeypatch):
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_order_statuses(app_code="myapp", order_ids=[])
    assert result == {}


@pytest.mark.asyncio
async def test_upsert_order_status_calls_execute_command():
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)

    await repo.upsert_order_status(
        order_id="ord-1",
        app_code="myapp",
        local_status="sent",
        tracking_number="TRK123",
        carrier_code="AusPost",
        shipped_at=None,
    )

    repo.execute_command.assert_awaited_once()
    args = repo.execute_command.call_args[0]
    assert args[1] == ("ord-1", "myapp", "sent", "TRK123", "AusPost", None)
