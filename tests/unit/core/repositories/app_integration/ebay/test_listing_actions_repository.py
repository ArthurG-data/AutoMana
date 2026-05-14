import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from automana.core.repositories.app_integration.ebay.listing_actions_repository import (
    EbayListingActionsRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ACTION_ID = UUID("00000000-0000-0000-0000-000000000002")


def make_repo():
    conn = MagicMock()
    repo = EbayListingActionsRepository.__new__(EbayListingActionsRepository)
    repo.connection = conn
    repo.executor = None
    return repo


@pytest.mark.asyncio
async def test_insert_action_returns_uuid():
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[{'id': str(ACTION_ID)}])

    result = await repo.insert_action(
        item_id="123456789",
        user_id=USER_ID,
        app_code="myapp",
        action_type="lower",
        strategy_kind="quick",
        suggested_price=9.99,
    )

    assert result == str(ACTION_ID)
    repo.execute_query.assert_awaited_once()
    args = repo.execute_query.call_args[0]
    assert args[1] == ("123456789", USER_ID, "myapp", "lower", "quick", 9.99)


@pytest.mark.asyncio
async def test_get_pending_returns_rows():
    repo = make_repo()
    fake_rows = [
        {'id': str(ACTION_ID), 'item_id': '111', 'user_id': str(USER_ID),
         'app_code': 'myapp', 'action_type': 'raise', 'strategy_kind': 'max',
         'suggested_price': 15.00, 'status': 'pending'}
    ]
    repo.execute_query = AsyncMock(return_value=fake_rows)

    result = await repo.get_pending(limit=50)

    assert len(result) == 1
    assert result[0]['action_type'] == 'raise'
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_done_calls_execute_command():
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)

    await repo.mark_done(action_id=ACTION_ID)

    repo.execute_command.assert_awaited_once()
    args = repo.execute_command.call_args[0]
    assert args[1][0] == ACTION_ID


@pytest.mark.asyncio
async def test_mark_failed_stores_error():
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)

    await repo.mark_failed(action_id=ACTION_ID, error="eBay timeout")

    repo.execute_command.assert_awaited_once()
    args = repo.execute_command.call_args[0]
    assert args[1] == ("eBay timeout", ACTION_ID)


@pytest.mark.asyncio
async def test_get_pending_for_item_returns_first_match():
    repo = make_repo()
    fake_row = {'id': str(ACTION_ID), 'item_id': '111', 'status': 'pending'}
    repo.execute_query = AsyncMock(return_value=[fake_row])

    result = await repo.get_pending_for_item(item_id="111")

    assert result == fake_row


@pytest.mark.asyncio
async def test_get_pending_for_item_returns_none_when_empty():
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[])

    result = await repo.get_pending_for_item(item_id="999")

    assert result is None
