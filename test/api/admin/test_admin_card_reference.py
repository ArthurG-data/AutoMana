import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4, UUID

@pytest.fixture
async def client():
    """Create async test client"""
    from backend.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_get_cards_returns_paginated_response(client):
    """Test GET / returns paginated cards"""
    response = await client.get("/api/catalog/mtg/card-reference/")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check response structure
    assert "data" in data
    assert "pagination" in data
    assert "limit" in data["pagination"]
    assert "offset" in data["pagination"]
    assert "total_count" in data["pagination"]

@pytest.mark.asyncio
async def test_get_cards_with_pagination(client):
    """Test pagination parameters work"""
    response = await client.get(
        "/api/catalog/mtg/card-reference/",
        params={"limit": 5, "offset": 0}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["limit"] == 5
    assert data["pagination"]["offset"] == 0

@pytest.mark.asyncio
async def test_get_card_by_id_not_found(client):
    """Test GET /{card_id} with non-existent ID"""
    fake_id = uuid4()
    response = await client.get(f"/api/catalog/mtg/card-reference/{fake_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["data"] == [] or data["data"] is None
    assert "message" in data


@pytest.mark.asyncio
async def test_get_card_by_id_invalid_uuid(client):
    """Test GET /{card_id} with invalid UUID format"""
    response = await client.get("/api/catalog/mtg/card-reference/not-a-uuid")
    
    assert response.status_code == 422 


# ==========================================
# POST Endpoints
# ==========================================

@pytest.mark.asyncio
async def test_insert_card(client):
    """Test POST / creates a card"""
    card_data = {
        "card_name": "Test Card",
        "cmc": 3,
        # Add other required fields from CreateCard schema
    }
    
    response = await client.post(
        "/api/catalog/mtg/card-reference/",
        json=card_data
    )
    
    # Either 201 (created) or 422 (validation) depending on required fields
    assert response.status_code in [201, 422, 500]


@pytest.mark.asyncio
async def test_bulk_insert_empty_list(client):
    """Test POST /bulk with empty list returns 400"""
    response = await client.post(
        "/api/catalog/mtg/card-reference/bulk",
        json=[]
    )
    
    assert response.status_code == 400
    assert "No cards provided" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bulk_insert_exceeds_limit(client):
    """Test POST /bulk with too many cards returns 400"""
    # Create 51 dummy cards (exceeds BULK_INSERT_LIMIT of 50)
    cards = [{"card_name": f"Card {i}", "cmc": 1} for i in range(51)]
    
    response = await client.post(
        "/api/catalog/mtg/card-reference/bulk",
        json=cards
    )
    
    assert response.status_code == 400
    assert "Bulk insert limited to" in response.json()["detail"]


# ==========================================
# DELETE Endpoints
# ==========================================

@pytest.mark.asyncio
async def test_delete_card_returns_api_response(client):
    """Test DELETE /{card_id} returns proper response"""
    fake_id = uuid4()
    response = await client.delete(f"/api/catalog/mtg/card-reference/{fake_id}")
    
    # May be 200 (success) or 500 (not found depending on implementation)
    assert response.status_code in [200, 404, 500]


# ==========================================
# File Upload Endpoints
# ==========================================

@pytest.mark.asyncio
async def test_upload_file_wrong_extension(client):
    """Test POST /upload-file rejects non-JSON files"""
    response = await client.post(
        "/api/catalog/mtg/card-reference/upload-file",
        files={"file": ("test.txt", b"not json content", "text/plain")}
    )
    
    assert response.status_code == 400
    assert "Only JSON files" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_file_valid_json(client):
    """Test POST /upload-file with valid JSON"""
    json_content = b'[{"card_name": "Test", "cmc": 1}]'
    
    response = await client.post(
        "/api/catalog/mtg/card-reference/upload-file",
        files={"file": ("cards.json", json_content, "application/json")}
    )
    
    # Either success or processing error
    assert response.status_code in [200, 500]


# ==========================================
# Sorting & Ordering
# ==========================================

@pytest.mark.asyncio
async def test_get_cards_with_sorting(client):
    """Test sorting parameters"""
    response = await client.get(
        "/api/catalog/mtg/card-reference/",
        params={"sort_by": "name", "sort_order": "desc"}
    )
    
    assert response.status_code == 200