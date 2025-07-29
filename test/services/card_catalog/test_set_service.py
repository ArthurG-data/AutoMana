import pytest
from unittest.mock import MagicMock, AsyncMock
from backend.new_services.card_catalog.set_service import get, list, add_set, add_sets_bulk
from backend.schemas.card_catalog.set import NewSet, BaseSet, SetInDB

@pytest.fixture
def mock_set_repo():
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
def sample_set_data():
    """Sample data for a set"""
    return {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "name": "Test Set",
        "code": "TS1",
        "set_type": "core",
        "released_at": "2023-01-01T00:00:00Z",
        "digital": False,
        "nonfoil_only": False,
        "foil_only": False,
        "parent_set_code": None,
        "icon_svg_uri": None
    }
@pytest.fixture
def sample_set_in_db_model():
    """Sample data for a set in the database"""
    return SetInDB(**sample_set_data())

@pytest.fixture
def sample_base_set_model():
    """Sample data for a base set"""
    return BaseSet(
        **sample_set_data()
    )

@pytest.mark.asyncio
async def test_get_set(mock_set_repo, sample_set_in_db_model):
    """Test retrieving a set by ID"""
    mock_set_repo.get.return_value = [sample_set_in_db_model.model_dump()]
    
    result = await get(mock_set_repo, sample_set_in_db_model.id)
    
    assert isinstance(result, SetInDB)
    assert result.set_name == sample_set_in_db_model.set_name
    mock_set_repo.get.assert_called_once_with(sample_set_in_db_model.id)

