from typing import Any
from uuid import UUID
import pytest
from unittest.mock import MagicMock, AsyncMock
from backend.new_services.card_catalog.set_service import (get
                                                           , add_set
                                                           , add_sets_bulk
                                                           , get_all
                                                           , get_many
                                                           , put_set
                                                           , get_parsed_set)
from backend.schemas.card_catalog.set import  BaseSet, SetInDB, NewSet,NewSets, UpdatedSet
from backend.exceptions.card_catalogue import set_exception

@pytest.fixture
def mock_set_repo():
    """Create a mock repository with AsyncMock methods"""
    repo = MagicMock()

    repo.get = AsyncMock()
    repo.get_many = AsyncMock()
    repo.add = AsyncMock()
    repo.add_many = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.get_all = AsyncMock()
    repo.get_many = AsyncMock()
    repo.list = AsyncMock()

    return repo

@pytest.fixture
def sample_set_data():
    """Sample data for a set"""
    return {
        "set_id": "123e4567-e89b-12d3-a456-426614174000",
        "set_name": "Test Set",
        "set_code": "TS1",
        "set_type": "core",
        "released_at": "2023-01-01T00:00:00Z",
        "digital": False,
        "foil_status_id": "foil",
    }


@pytest.mark.asyncio
async def test_get_set_success(mock_set_repo: MagicMock, sample_set_data):
    """Test retrieving a set by ID"""
    mock_set_repo.get.return_value = SetInDB(**sample_set_data)

    result = await get(mock_set_repo, sample_set_data['set_id'])
    
    assert isinstance(result, SetInDB)
 
    mock_set_repo.get.assert_called_once_with(sample_set_data['set_id'])

@pytest.mark.asyncio
async def test_get_set_not_found(mock_set_repo: MagicMock, sample_set_data: dict[str,  Any]):
    """Test retrieving a set by ID that does not exist"""
    mock_set_repo.get.return_value = None

    with pytest.raises(set_exception.SetNotFoundError):
        await get(mock_set_repo, sample_set_data['set_id'])

    mock_set_repo.get.assert_called_once_with(sample_set_data['set_id'])

@pytest.mark.asyncio
async def test_get_all_sets_success(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test retrieving all sets"""
    mock_set_repo.list.return_value = [SetInDB(**sample_set_data)]

    result = await get_all(mock_set_repo)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], SetInDB)

@pytest.mark.asyncio
async def test_get_all_sets_empty(mock_set_repo: MagicMock):
    """Test retrieving all sets when no sets exist"""
    mock_set_repo.list.return_value = []
    with pytest.raises(set_exception.SetNotFoundError):
        await get_all(mock_set_repo)

@pytest.mark.asyncio
async def test_get_all_sets_connection_error(mock_set_repo: MagicMock):
    """Test connection error during retrieval of all sets"""
    mock_set_repo.list.side_effect = Exception("Database connection error")
    with pytest.raises(set_exception.SetRetrievalError):
        await get_all(mock_set_repo)

@pytest.mark.asyncio
async def test_get_many_sets_success(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test retrieving multiple sets by IDs"""
    mock_set_repo.list.return_value = [SetInDB(**sample_set_data)]

    result = await get_many(mock_set_repo, [sample_set_data['set_id']])

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], SetInDB)

@pytest.mark.asyncio
async def test_get_many_sets_not_found(mock_set_repo: MagicMock):
    """Test retrieving multiple sets by IDs when none exist"""
    mock_set_repo.list.return_value = []
    with pytest.raises(set_exception.SetNotFoundError):
        await get_many(mock_set_repo, ["123e4567-e89b-12d3-a456-426614174000"])

@pytest.mark.asyncio
async def test_get_many_sets_connection_error(mock_set_repo: MagicMock):
    """Test connection error during retrieval of multiple sets"""
    mock_set_repo.list.side_effect = Exception("Database connection error")
    with pytest.raises(set_exception.SetRetrievalError):
        await get_many(mock_set_repo, ["123e4567-e89b-12d3-a456-426614174000"]) 

@pytest.mark.asyncio
async def test_add_set_success(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test adding a new set"""
    mock_set_repo.add.return_value =sample_set_data

    new_set = NewSet(**sample_set_data)
    result = await add_set(mock_set_repo, new_set)

    assert isinstance(result, SetInDB)
    assert str(result.set_id)  == sample_set_data['set_id']

    mock_set_repo.add.assert_called_once_with(new_set.create_values())

@pytest.mark.asyncio
async def test_add_set_failure(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test adding a new set that fails"""
    mock_set_repo.add.side_effect = set_exception.SetCreationError("Failed to create set")

    new_set = NewSet(**sample_set_data)
    with pytest.raises(set_exception.SetCreationError):
        await add_set(mock_set_repo, new_set)

    mock_set_repo.add.assert_called_once_with(new_set.create_values())

@pytest.mark.asyncio
async def test_add_sets_many_success(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test adding multiple new sets"""
    mock_set_repo.add_many.return_value = [sample_set_data]

    new_sets = NewSets(items=[NewSet(**sample_set_data)])
    result = await add_sets_bulk(mock_set_repo, new_sets)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], SetInDB)
    data = [set.create_values() for set in new_sets]
    mock_set_repo.add_many.assert_called_once_with(data)

@pytest.mark.asyncio
async def test_add_sets_many_failure(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test adding multiple new sets that fails"""
    mock_set_repo.add_many.side_effect = set_exception.SetCreationError("Failed to create sets")

    new_sets = NewSets(items=[NewSet(**sample_set_data)])
    with pytest.raises(set_exception.SetCreationError):
        await add_sets_bulk(mock_set_repo, new_sets)
    data = [set.create_values() for set in new_sets]
    mock_set_repo.add_many.assert_called_once_with(data)

@pytest.mark.asyncio
async def test_add_sets_many_connection_error(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test connection error during adding multiple sets"""
    mock_set_repo.add_many.side_effect = Exception("Database connection error")

    new_sets = NewSets(items=[NewSet(**sample_set_data)])
    with pytest.raises(set_exception.SetCreationError):
        await add_sets_bulk(mock_set_repo, new_sets)
    data = [set.create_values() for set in new_sets]
    mock_set_repo.add_many.assert_called_once_with(data)

@pytest.mark.asyncio
async def test_put_set_success(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test updating an existing set"""
    mock_set_repo.update.return_value = sample_set_data

    update_set = UpdatedSet(**sample_set_data)
    result = await put_set(mock_set_repo, sample_set_data['set_id'], update_set)

    assert isinstance(result, SetInDB)
    assert str(result.set_id) == sample_set_data['set_id']
    not_nul = {k : v for k,v in update_set.model_dump().items() if v != None}
    mock_set_repo.update.assert_called_once_with(sample_set_data['set_id'], not_nul )

@pytest.mark.asyncio
async def test_put_set_not_found(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test updating a set that does not exist"""
    mock_set_repo.update.side_effect = set_exception.SetNotFoundError("Set not found")
    update_set = UpdatedSet(**sample_set_data)
    with pytest.raises(set_exception.SetNotFoundError):
        await put_set(mock_set_repo, sample_set_data['set_id'], update_set)
    not_nul = {k : v for k,v in update_set.model_dump().items() if v != None}
    mock_set_repo.update.assert_called_once_with(sample_set_data['set_id'], not_nul)

@pytest.mark.asyncio
async def test_put_set_connection_error(mock_set_repo: MagicMock, sample_set_data: dict[str, Any]):
    """Test connection error during updating a set"""
    mock_set_repo.update.side_effect = Exception("Database connection error")
    update_set = UpdatedSet(**sample_set_data)
    with pytest.raises(set_exception.SetUpdateError):
        await put_set(mock_set_repo, sample_set_data['set_id'], update_set)
    not_nul = {k : v for k,v in update_set.model_dump().items() if v != None}
    mock_set_repo.update.assert_called_once_with(sample_set_data['set_id'], not_nul)

@pytest.mark.asyncio
async def test_get_parsed_set_success():
    """Test parsing sets from JSON file"""
    sample_json = b'[{"set_id": "123e4567-e89b-12d3-a456-426614174000", "set_name": "Test Set", "set_code": "TS1", "set_type": "core", "released_at": "2023-01-01", "digital": false}]'
    
   
    result = await get_parsed_set(sample_json)
    
    assert isinstance(result, NewSets)
    assert len(result.items) == 1
    assert result.items[0].set_id == UUID("123e4567-e89b-12d3-a456-426614174000")
    
@pytest.mark.asyncio
async def test_get_parsed_set_failure():
    """Test failure in parsing sets from JSON file"""
    invalid_json = b'{"invalid": "data"}'
    
    with pytest.raises(set_exception.SetParsingError):
        await get_parsed_set(invalid_json)