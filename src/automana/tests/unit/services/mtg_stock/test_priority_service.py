import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_get_tier_print_ids_delegates_to_repo():
    from automana.core.services.app_integration.mtg_stock.priority_service import (
        get_tier_print_ids,
    )
    repo = MagicMock()
    repo.fetch_tier_print_ids = AsyncMock(return_value=[10, 20, 30])

    result = await get_tier_print_ids(
        mtg_stock_priority_repository=repo,
        tier=1,
    )

    assert result == {"print_ids": [10, 20, 30]}
    repo.fetch_tier_print_ids.assert_awaited_once_with(1)
