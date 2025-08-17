import pytest
from fastapi.testclient import TestClient
from uuid import UUID, uuid4
from unittest.mock import patch, AsyncMock

from backend.main import app
from backend.schemas.card_catalog.card import CreateCard, CardResponse

client = TestClient(app)

# Test data
test_card_data = {
    "name": "Black Lotus",
    "mana_cost": "{0}",
    "cmc": 0,
    "type_line": "Artifact",
    "oracle_text": "Sacrifice Black Lotus: Add three mana of any one color.",
    "colors": [],
    "color_identity": [],
    "rarity": "rare",
    "set_code": "lea"
}

test_card_response = {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "name": "Black Lotus",
    "mana_cost": "{0}",
    "cmc": 0,
    "type_line": "Artifact",
    "oracle_text": "Sacrifice Black Lotus: Add three mana of any one color.",
    "colors": [],
    "color_identity": [],
    "rarity": "rare",
    "set_code": "lea",
    "created_at": "2025-08-04T12:00:00"
}

@pytest.mark.asyncio
@patch('backend.services.service_manager.ServiceManager.execute_service')
async def test_insert_card_success(mock_execute_service):
    """Test successful card creation"""
    # Setup mock
    mock_execute_service.return_value = test_card_response
    
    # Execute request
    response = client.post("/admin/card-reference/", json=test_card_data)
    
    # Assertions
    assert response.status_code == 201
    assert response.json() == test_card_response
    
    # Verify service was called with correct parameters
    mock_execute_service.assert_called_once_with(
        "card_catalog.card.create",
        card=CreateCard(**test_card_data)
    )
