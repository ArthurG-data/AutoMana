import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4
from backend.new_services.card_catalog.collection_service import (
    get_collection_by_id,
    add,
    get,
    get_many,
    update_collection,
    delete_collection
)
from backend.schemas.collections.collection import CreateCollection, PublicCollection, UpdateCollection
from backend.schemas.user_management.user import UserInDB
from backend.exceptions import card_catalog_exceptions
from datetime import datetime

@pytest.fixture
def mock_collection_repo():
    """Create a mock repository with AsyncMock methods"""
    repo = MagicMock()
    repo.get = AsyncMock()
    repo.get_many = AsyncMock()
    repo.add = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    return repo

@pytest.fixture
def test_user():
    """Test user with UserInDB structure"""
    return UserInDB(
        unique_id=uuid4(),
        username="testuser",
        email="test@example.com",
        disabled=False,
        role="user"
    )

@pytest.fixture
def test_collection_data():
    return PublicCollection(
        collection_id=str(uuid4()),
        user_id=str(uuid4()),
        name="Test Collection",
        description="A test collection",
        is_public=True,
        created_at="2023-01-01T00:00:00Z",
        updated_at="2023-01-01T00:00:00Z"
    )

@pytest.fixture
def test_update_collection():
    """Test update collection model"""
    return UpdateCollection(
        name="Updated Collection",
        description="Updated description",
        is_public=False
    )

@pytest.fixture
def test_collection_model():
    """Test collection as CreateCollection model"""
    return CreateCollection(
        name="Test Collection",
        description="A test collection",
        is_public=True
    )

@pytest.mark.service
async def test_add_collection_success(mock_collection_repo, test_user, test_collection):
    # Setup mock return value
    collection_id = uuid4()
    mock_collection_repo.add.return_value = collection_id
    
    # Call service
    result = await add(mock_collection_repo, test_collection_model, test_user)
    
    # Assertions
    assert isinstance(result, dict)
    assert "collection_id" in result
    assert result["collection_id"] == str(collection_id)
    assert result["name"] == test_collection_model.name
    
    # Verify repository was called correctly
    mock_collection_repo.add.assert_called_once_with(
        test_user.unique_id, test_collection_model
    )
    
@pytest.mark.service
async def test_add_collection_failure(mock_collection_repo, test_user, test_collection_model):
    """Test handling of collection creation failure"""
    # Setup
    mock_collection_repo.add.side_effect = Exception("Database error")
    
    # Execute and Assert
    with pytest.raises(card_catalog_exceptions.CollectionCreationError):
        await add(mock_collection_repo, test_collection_model, test_user)
