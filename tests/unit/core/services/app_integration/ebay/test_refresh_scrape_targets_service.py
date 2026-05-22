import pytest
from unittest.mock import AsyncMock, patch

from automana.core.services.app_integration.ebay.refresh_scrape_targets_service import (
    refresh_scrape_targets,
)


@pytest.mark.asyncio
async def test_refresh_scrape_targets_calls_repo_with_min_cents():
    mock_repo = AsyncMock()
    with patch(
        "automana.core.services.app_integration.ebay.refresh_scrape_targets_service.get_settings",
        return_value=type("S", (), {"ebay_scrape_target_min_cents": 200})(),
    ):
        result = await refresh_scrape_targets(ebay_scrape_repository=mock_repo)

    mock_repo.deactivate_stale_targets.assert_called_once_with(min_cents=200)
    mock_repo.refresh_scrape_targets.assert_called_once_with(min_cents=200)
    assert result["min_cents"] == 200


@pytest.mark.asyncio
async def test_refresh_scrape_targets_uses_default_when_setting_absent():
    mock_repo = AsyncMock()
    with patch(
        "automana.core.services.app_integration.ebay.refresh_scrape_targets_service.get_settings",
        return_value=type("S", (), {})(),   # no ebay_scrape_target_min_cents attr
    ):
        result = await refresh_scrape_targets(ebay_scrape_repository=mock_repo)

    mock_repo.deactivate_stale_targets.assert_called_once_with(min_cents=100)
    mock_repo.refresh_scrape_targets.assert_called_once_with(min_cents=100)
    assert result["min_cents"] == 100


@pytest.mark.asyncio
async def test_deactivate_called_before_refresh():
    """deactivate_stale_targets must run before refresh_scrape_targets."""
    call_order = []
    mock_repo = AsyncMock()
    mock_repo.deactivate_stale_targets.side_effect = lambda **_: call_order.append("deactivate")
    mock_repo.refresh_scrape_targets.side_effect = lambda **_: call_order.append("refresh")
    with patch(
        "automana.core.services.app_integration.ebay.refresh_scrape_targets_service.get_settings",
        return_value=type("S", (), {"ebay_scrape_target_min_cents": 100})(),
    ):
        await refresh_scrape_targets(ebay_scrape_repository=mock_repo)

    assert call_order == ["deactivate", "refresh"]
