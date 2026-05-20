"""
Integration tests for collection entries pagination.

Tests verify that the list_entries endpoint correctly handles limit/offset pagination:
- Default page size is 50
- limit parameter is respected
- offset advances through pages without overlap
- Offsetting past the end returns empty list gracefully
"""
import pytest


pytestmark = [pytest.mark.integration, pytest.mark.api]


@pytest.mark.asyncio
async def test_entries_default_limit_returns_at_most_50(client, auth_headers, seeded_collection):
    """Default page size is 50."""
    collection_id = seeded_collection["collection_id"]
    response = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) <= 50


@pytest.mark.asyncio
async def test_entries_limit_param_is_respected(client, auth_headers, seeded_collection):
    """?limit=5 returns at most 5 entries."""
    collection_id = seeded_collection["collection_id"]
    response = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) <= 5


@pytest.mark.asyncio
async def test_entries_offset_advances_page(client, auth_headers, seeded_collection):
    """Page 1 and page 2 return different items."""
    collection_id = seeded_collection["collection_id"]
    r1 = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5&offset=0",
        headers=auth_headers,
    )
    r2 = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5&offset=5",
        headers=auth_headers,
    )
    ids1 = {e["item_id"] for e in r1.json()["data"]}
    ids2 = {e["item_id"] for e in r2.json()["data"]}
    assert ids1.isdisjoint(ids2), "Pages must not overlap"


@pytest.mark.asyncio
async def test_entries_exhaustion_returns_empty_list(client, auth_headers, seeded_collection):
    """Offset past the last entry returns an empty list, not an error."""
    collection_id = seeded_collection["collection_id"]
    response = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5&offset=99999",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
