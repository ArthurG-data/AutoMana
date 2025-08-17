import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4
from backend.new_services.card_catalog.collection_service import (
    get_collection_by_id,
    add,
    get,
    get_many,
    update_collection,
    delete_collection,
    get_all_collections
)
from backend.schemas.collections.collection import CreateCollection, PublicCollection, CollectionInDB, UpdateCollection
from backend.schemas.user_management.user import UserInDB
from backend.exceptions.card_catalogue import card_catalog_exceptions
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
    repo.get_all = AsyncMock()
    return repo

@pytest.fixture
def test_user():
    """Test user with UserInDB structure"""
    return {
        "unique_id": "550e8400-e29b-41d4-a716-446655440001",
        "username": "testuser1",
        "email": "test1@example.com", 
        "disabled": False,
        "role": "user"
    }

@pytest.fixture
def test_user_many():
    """Test user with UserInDB structure"""
    return [{
        "unique_id": "550e8400-e29b-41d4-a716-446655440002",
        "username": "testuser2",
        "email": "test2@example.com", 
        "disabled": False,
        "role": "user"
    }, {
        "unique_id": "550e8400-e29b-41d4-a716-446655440001",
        "username": "testuser1",
        "email": "test1@example.com", 
        "disabled": False,
        "role": "user"
    }]

@pytest.fixture
def test_collection_data_user():
    """Test collection data as a dictionary"""
    return {
        "collection_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "550e8400-e29b-41d4-a716-446655440001",
        "collection_name": "Test Collection 1",
        "is_active": True,
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z"
    }

@pytest.fixture
def test_collection1_data_user1():
    """Test collection data as a dictionary"""
    return {
        "collection_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "550e8400-e29b-41d4-a716-446655440001",
        "collection_name": "Test Collection 1",
        "is_active": True,
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z"
    }

@pytest.fixture
def test_collection2_data_user1():
    """Test collection data as a dictionary"""
    return {
        "collection_id": "550e8400-e29b-41d4-a716-446655440002",
        "user_id": "550e8400-e29b-41d4-a716-446655440001",
        "collection_name": "Test Collection 2",
        "is_active": True,
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z"
    }

@pytest.fixture
def test_collection1_data_user2():
    """Test collection data as a dictionary"""
    return {
        "collection_id": "550e8400-e29b-41d4-a716-446655440003",
        "user_id": "550e8400-e29b-41d4-a716-446655440002",
        "collection_name": "Test Collection 2",
        "is_active": True,
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z"
    }

@pytest.fixture
def test_update_collection():
    """Test update collection model"""
    return UpdateCollection(
        name="Updated Collection",
        description="Updated description",
        is_public=False
    )

@pytest.fixture
def test_collection():
    """Test collection as CreateCollection model"""
    return CreateCollection(
        collection_name="Test Collection 1",
        user_id=UUID("550e8400-e29b-41d4-a716-446655440001")
    )

"""def test_[unit_being_tested]_[scenario/condition]_[expected_result]():"""
def test_always_passes():
    assert True

@pytest.mark.asyncio
async def test_get_collection_by_id_success(mock_collection_repo, test_collection1_data_user1):
    mock_collection_repo.get.return_value = test_collection1_data_user1

    result = await get_collection_by_id(mock_collection_repo, test_collection1_data_user1["collection_id"])

    assert result == test_collection1_data_user1
    mock_collection_repo.get.assert_called_once_with(test_collection1_data_user1["collection_id"])

@pytest.mark.asyncio
async def test_get_collection_by_id_not_found(mock_collection_repo):
    mock_collection_repo.get.return_value = None

    with pytest.raises(card_catalog_exceptions.CollectionNotFoundError):
        await get_collection_by_id(mock_collection_repo, str(uuid4()))

@pytest.mark.asyncio
async def test_add_collection_success(mock_collection_repo, test_collection, test_collection_data_user):
    mock_collection_repo.add.return_value = test_collection_data_user
    result = await add(mock_collection_repo, test_collection)
    result = CollectionInDB.model_validate(result)
    assert isinstance(result, CollectionInDB)
    mock_collection_repo.add.assert_called_once_with(test_collection.collection_name, test_collection.user_id)

@pytest.mark.asyncio
async def test_add_collection_failure(mock_collection_repo, test_collection):
    mock_collection_repo.add.return_value = None
    with pytest.raises(card_catalog_exceptions.CollectionCreationError):
        await add(mock_collection_repo, test_collection)

@pytest.mark.asyncio
async def test_get_collection_success(mock_collection_repo, test_collection1_data_user1, test_user):
    #set output as a dictionary
    mock_collection_repo.get.return_value = test_collection1_data_user1
    collection_id = test_collection1_data_user1["collection_id"]
    user_id = test_user["unique_id"]
    # return a CollectionInDB object
    result = await get(mock_collection_repo, collection_id, user_id)
    assert isinstance(result, CollectionInDB)
    assert result == CollectionInDB(**test_collection1_data_user1)
    mock_collection_repo.get.assert_called_once_with(collection_id, user_id)

@pytest.mark.asyncio
async def test_get_collection_not_found(mock_collection_repo, test_user):
    mock_collection_repo.get.return_value = None
    collection_id = str(uuid4())
    user_id = test_user["unique_id"]
    with pytest.raises(card_catalog_exceptions.CollectionNotFoundError):
        await get(mock_collection_repo, collection_id, user_id)

@pytest.mark.asyncio
async def test_get_collection_access_denied(mock_collection_repo, test_collection1_data_user1, test_user):
    mock_collection_repo.get.return_value = test_collection1_data_user1
    
    collection_owner_id = test_collection1_data_user1["user_id"]
    # Simulate a different user trying to access the collection
    different_user_id = str(uuid4())
    while different_user_id == collection_owner_id:
        different_user_id = str(uuid4())
    
    collection_id = test_collection1_data_user1["collection_id"]

    with pytest.raises(card_catalog_exceptions.CollectionAccessDeniedError):
        await get(mock_collection_repo, collection_id, different_user_id)

@pytest.mark.asyncio
async def test_get_all_collections_success(mock_collection_repo, test_collection1_data_user1, test_collection2_data_user1, test_user):
    #test a user if 2 collections exist
    mock_collection_repo.get_all.return_value = [test_collection1_data_user1, test_collection2_data_user1]
    
    user_id = test_user["unique_id"]
    result = await get_all_collections(mock_collection_repo, user_id)

    assert isinstance(result, list)
    assert len(result) > 0
    mock_collection_repo.get_all.assert_called_once_with(user_id)

@pytest.mark.asyncio
async def test_get_all_collections_no_valid_user(mock_collection_repo, test_user):
    #test a user if no collections ex  ist
    mock_collection_repo.get_all.return_value = []
    
    user_id = test_user["unique_id"]
    with pytest.raises(card_catalog_exceptions.CollectionNotFoundError):
        await get_all_collections(mock_collection_repo, user_id)

@pytest.mark.asyncio
async def test_get_many_no_collections_found(mock_collection_repo, test_user):
    #test a user if no collections exist
    mock_collection_repo.get_many.return_value = []
    user_id = test_user["unique_id"]
    with pytest.raises(card_catalog_exceptions.CollectionNotFoundError):
        await get_many(mock_collection_repo, user_id, [UUID('550e8400-e29b-41d4-a716-446655440001'), UUID('550e8400-e29b-41d4-a716-446655440002')])

@pytest.mark.asyncio
async def test_delete_collection_success(mock_collection_repo, test_collection1_data_user1, test_user):
    mock_collection_repo.delete.return_value = True
    mock_collection_repo.get.return_value = None
    collection_id = test_collection1_data_user1["collection_id"]
    user_id = test_user["unique_id"]
    
    result = await delete_collection(mock_collection_repo, collection_id, user_id)
    
    assert result is True
    mock_collection_repo.delete.assert_called_once_with(collection_id, user_id)

pytest.mark.asyncio
async def test_delete_collection_not_found(mock_collection_repo, test_user):
    mock_collection_repo.delete.return_value = None
    mock_collection_repo.get.return_value = None
    collection_id = str(uuid4())
    user_id = test_user["unique_id"]
    with pytest.raises(card_catalog_exceptions.CollectionNotFoundError):
        await delete_collection(mock_collection_repo, collection_id, user_id)

pytest.mark.asyncio
async def test_delete_collection_not_deleted(mock_collection_repo,test_collection1_data_user1, test_user):
    mock_collection_repo.delete.return_value = None
    mock_collection_repo.get.return_value = test_collection1_data_user1
    collection_id = test_collection1_data_user1["collection_id"]
    user_id = test_user["unique_id"]
    with pytest.raises(card_catalog_exceptions.CollectionNotFoundError):
        await delete_collection(mock_collection_repo, collection_id, user_id)
