"""Unit tests for EbayFindingAPIRepository pagination and keyword=None behaviour."""
from __future__ import annotations

import pytest
from unittest.mock import patch

pytestmark = pytest.mark.asyncio


async def test_pagination_collects_items_across_pages():
    """max_pages=5 with totalPages=2 should call _fetch_page twice and return combined items."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    page_responses = [
        ([{"item_id": "A", "title": "Card A", "price": 10.0, "currency": "USD",
           "condition": "Used", "url": None, "sold_date": "2026-05-24T10:00:00Z"}], 2),
        ([{"item_id": "B", "title": "Card B", "price": 12.0, "currency": "USD",
           "condition": "New", "url": None, "sold_date": "2026-05-24T11:00:00Z"}], 2),
    ]
    call_idx = 0

    async def fake_fetch_page(params):
        nonlocal call_idx
        result = page_responses[call_idx]
        call_idx += 1
        return result

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        items = await repo.find_completed_items("Sheoldred", "app-id", max_pages=5)

    assert len(items) == 2
    assert call_idx == 2  # stopped at total_pages=2, not max_pages=5


async def test_pagination_stops_early_on_empty_page():
    """If a page returns 0 items, no further pages are fetched."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    call_idx = 0

    async def fake_fetch_page(params):
        nonlocal call_idx
        call_idx += 1
        return ([], 10)  # 0 items but totalPages=10

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        items = await repo.find_completed_items("Sheoldred", "app-id", max_pages=5)

    assert items == []
    assert call_idx == 1  # stopped after first empty page


async def test_keywords_none_omits_param_from_request():
    """keywords=None must not include a 'keywords' key in the Finding API params."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    captured: dict = {}

    async def fake_fetch_page(params):
        captured.update(params)
        return ([], 1)

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        await repo.find_completed_items(None, "app-id")

    assert "keywords" not in captured


async def test_keywords_str_includes_param_in_request():
    """keywords='Sheoldred' must appear in the Finding API params."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    captured: dict = {}

    async def fake_fetch_page(params):
        captured.update(params)
        return ([], 1)

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        await repo.find_completed_items("Sheoldred", "app-id")

    assert captured.get("keywords") == "Sheoldred"


async def test_on_page_fetched_called_once_per_page():
    """on_page_fetched callback is invoked exactly once per successfully fetched page."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    page_responses = [
        ([{"item_id": "A", "title": "Card A", "price": 10.0, "currency": "USD",
           "condition": "Used", "url": None, "sold_date": "2026-05-24T10:00:00Z"}], 2),
        ([{"item_id": "B", "title": "Card B", "price": 12.0, "currency": "USD",
           "condition": "New", "url": None, "sold_date": "2026-05-24T11:00:00Z"}], 2),
    ]
    call_idx = 0

    async def fake_fetch_page(params):
        nonlocal call_idx
        result = page_responses[call_idx]
        call_idx += 1
        return result

    callback_count = 0

    async def on_page():
        nonlocal callback_count
        callback_count += 1

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        await repo.find_completed_items("Sheoldred", "app-id", max_pages=5, on_page_fetched=on_page)

    assert callback_count == 2, f"Expected 2 callbacks (one per page), got {callback_count}"
