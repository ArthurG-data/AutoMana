import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from automana.core.services.app_integration.ebay.listing_actions_service import (
    stage_action,
    get_pending_action,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ACTION_ID = UUID("00000000-0000-0000-0000-000000000002")


def make_repo():
    repo = MagicMock()
    return repo


@pytest.mark.asyncio
async def test_stage_action_creates_new():
    repo = make_repo()
    repo.get_pending_for_item = AsyncMock(return_value=None)
    repo.insert_action = AsyncMock(return_value=str(ACTION_ID))

    result = await stage_action(
        listing_actions_repository=repo,
        user_id=USER_ID,
        app_code="test_app",
        item_id="item-123",
        action_type="lower",
        strategy_kind="quick",
        suggested_price=9.99,
    )

    assert result == {"action_id": str(ACTION_ID), "created": True}
    repo.get_pending_for_item.assert_called_once_with("item-123")
    repo.insert_action.assert_called_once_with(
        "item-123", USER_ID, "test_app", "lower", "quick", 9.99
    )


@pytest.mark.asyncio
async def test_stage_action_returns_existing():
    repo = make_repo()
    existing_row = {
        "id": str(ACTION_ID),
        "item_id": "item-123",
        "action_type": "lower",
        "status": "pending",
    }
    repo.get_pending_for_item = AsyncMock(return_value=existing_row)
    repo.insert_action = AsyncMock()

    result = await stage_action(
        listing_actions_repository=repo,
        user_id=USER_ID,
        app_code="test_app",
        item_id="item-123",
        action_type="lower",
        strategy_kind="quick",
        suggested_price=9.99,
    )

    assert result == {"action_id": str(ACTION_ID), "created": False}
    repo.get_pending_for_item.assert_called_once_with("item-123")
    repo.insert_action.assert_not_called()


@pytest.mark.asyncio
async def test_get_pending_action_returns_row():
    repo = make_repo()
    pending_row = {
        "id": str(ACTION_ID),
        "item_id": "item-456",
        "action_type": "raise",
        "status": "pending",
    }
    repo.get_pending_for_item = AsyncMock(return_value=pending_row)

    result = await get_pending_action(
        listing_actions_repository=repo,
        item_id="item-456",
    )

    assert result == pending_row
    repo.get_pending_for_item.assert_called_once_with("item-456")


@pytest.mark.asyncio
async def test_get_pending_action_returns_none():
    repo = make_repo()
    repo.get_pending_for_item = AsyncMock(return_value=None)

    result = await get_pending_action(
        listing_actions_repository=repo,
        item_id="item-789",
    )

    assert result is None
    repo.get_pending_for_item.assert_called_once_with("item-789")
