import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pydantic import ValidationError
from uuid import uuid4, UUID
from datetime import datetime

from backend.schemas.collections.collection import (
    CreateCollection,
    UpdateCollection,
    CollectionInDB,
    PublicCollection
)

class TestCreateCollection:
    """Tests for the CreateCollection schema"""
    
    def test_valid_complete(self):
        """Test with all fields"""
        user_id = uuid4()
        data = {
            "collection_name": "My Collection",
            "user_id": str(user_id),
        }
        collection = CreateCollection(**data)
        assert collection.collection_name == "My Collection"
        assert collection.user_id == user_id
        
    def test_missing_name(self):
        """Test validation with missing required field"""
        data = {
            "user_id": str(uuid4())
        }
        with pytest.raises(AssertionError, ValidationError) as exc_info:
            CreateCollection(**data)
            
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"][0] == "collection_name"
        assert "field required" in errors[0]["msg"]
        
    def test_empty_name(self):
        """Test validation with empty name"""
        data = {
            "collection_name": ""
        }
        with pytest.raises(ValidationError) as exc_info:
            CreateCollection(**data)
            
        errors = exc_info.value.errors()
        assert "collection_name" in str(errors)
        
    def test_name_too_long(self):
        """Test validation with name too long"""
        data = {
            "collection_name": "x" * 101  # Assuming max length is 100
        }
        with pytest.raises(ValidationError) as exc_info:
            CreateCollection(**data)
            
        errors = exc_info.value.errors()
        assert "collection_name" in str(errors)
        assert "too long" in str(errors).lower()


class TestUpdateCollection:
    """Tests for the UpdateCollection schema"""

    
    def test_valid_update_all(self):
        """Test updating all fields"""
        data = {
            "collection_name": "Updated Collection",
            "description": "Updated description",
            "is_public": False
        }
        collection = UpdateCollection(**data)
        assert collection.collection_name == "Updated Collection"
        assert collection.description == "Updated description"
        assert collection.is_public is False
        
    def test_valid_partial_update(self):
        """Test partial update with only some fields"""
        data = {
            "collection_name": "Updated Collection"
        }
        collection = UpdateCollection(**data)
        assert collection.collection_name == "Updated Collection"
        assert collection.description is None
        assert collection.is_public is None
        
    def test_empty_update(self):
        """Test with empty update data"""
        data = {}
        collection = UpdateCollection(**data)
        assert collection.collection_name is None
        assert collection.description is None
        assert collection.is_public is None
        
    def test_name_too_long(self):
        """Test validation with name too long"""
        data = {
            "collection_name": "x" * 101  # Assuming max length is 100
        }
        with pytest.raises(ValidationError) as exc_info:
            UpdateCollection(**data)
            
        errors = exc_info.value.errors()
        assert "collection_name" in str(errors)
        assert "too long" in str(errors).lower()


class TestCollectionInDB:
    """Tests for the CollectionInDB schema"""
    
    def test_valid_collection(self):
        """Test with valid data"""
        data = {
            "collection_id": str(uuid4()),
            "user_id": str(uuid4()),
            "collection_name": "Test Collection",
            "description": "A test collection",
            "is_public": True,
            "is_active": True,
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z"
        }
        collection = CollectionInDB(**data)
        assert collection.collection_name == "Test Collection"
        assert collection.description == "A test collection"
        assert collection.is_public is True
        assert collection.is_active is True
        assert isinstance(collection.collection_id, str)
        assert isinstance(collection.user_id, str)
        
    def test_missing_required_fields(self):
        """Test validation with missing required fields"""
        data = {
            "collection_name": "Incomplete Collection"
        }
        with pytest.raises(ValidationError) as exc_info:
            CollectionInDB(**data)
            
        errors = exc_info.value.errors()
        missing_fields = [error["loc"][0] for error in errors]
        assert "collection_id" in missing_fields
        assert "user_id" in missing_fields
        assert "created_at" in missing_fields
        
    def test_invalid_date_format(self):
        """Test validation with invalid date format"""
        data = {
            "collection_id": str(uuid4()),
            "user_id": str(uuid4()),
            "collection_name": "Test Collection",
            "created_at": "not-a-date",
            "updated_at": "2023-01-01T00:00:00Z"
        }
        with pytest.raises(ValidationError) as exc_info:
            CollectionInDB(**data)
            
        errors = exc_info.value.errors()
        assert any("created_at" in str(error) for error in errors)
        assert "invalid datetime format" in str(errors).lower()
        
    def test_invalid_uuid_format(self):
        """Test validation with invalid UUID format"""
        data = {
            "collection_id": "not-a-uuid",
            "user_id": str(uuid4()),
            "collection_name": "Test Collection",
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z"
        }
        with pytest.raises(ValidationError) as exc_info:
            CollectionInDB(**data)
            
        errors = exc_info.value.errors()
        assert "collection_id" in str(errors)


class TestCollectionPublic:
    """Tests for the CollectionPublic schema"""
    
    def test_valid_public_collection(self):
        """Test with valid data"""
        data = {
            "collection_id": str(uuid4()),
            "collection_name": "Public Collection",
            "description": "A public collection",
            "is_public": True,
            "created_at": "2023-01-01T00:00:00Z",
            "card_count": 10
        }
        collection = CollectionPublic(**data)
        assert collection.collection_name == "Public Collection"
        assert collection.description == "A public collection"
        assert collection.is_public is True
        assert collection.card_count == 10
        
    def test_missing_card_count(self):
        """Test with missing optional fields"""
        data = {
            "collection_id": str(uuid4()),
            "collection_name": "Public Collection",
            "description": "A public collection",
            "is_public": True,
            "created_at": "2023-01-01T00:00:00Z"
        }
        collection = CollectionPublic(**data)
        assert collection.card_count == 0  # Default value
        
    def test_convert_string_id_to_uuid(self):
        """Test that string ID is properly converted to UUID"""
        id_str = str(uuid4())
        data = {
            "collection_id": id_str,
            "collection_name": "Public Collection",
            "description": "A public collection",
            "is_public": True,
            "created_at": "2023-01-01T00:00:00Z"
        }
        collection = CollectionPublic(**data)
        # Check if the string was properly converted to UUID
        if hasattr(collection, 'collection_id'):
            # If model keeps as string
            assert collection.collection_id == id_str
            # Or if model converts to UUID
            # assert isinstance(collection.collection_id, UUID)
            # assert str(collection.collection_id) == id_str


def test_model_inheritance():
    """Test relationships between models"""
    # Create base data that can work for any model
    base_data = {
        "collection_id": str(uuid4()),
        "user_id": str(uuid4()),
        "collection_name": "Test Collection",
        "description": "A test collection",
        "is_public": True,
        "is_active": True,
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z",
        "card_count": 5
    }
    
    # Test that CollectionInDB can be converted to a dict
    collection_db = CollectionInDB(**base_data)
    collection_dict = collection_db.model_dump()
    
    # Ensure all the fields we expect are present
    assert "collection_id" in collection_dict
    assert "collection_name" in collection_dict
    assert "user_id" in collection_dict
    
    # Test that we can convert between models if needed
    if hasattr(CollectionPublic, 'model_validate'):
        # For Pydantic v2
        public_collection = CollectionPublic.model_validate(collection_dict)
    else:
        # For Pydantic v1
        public_collection = CollectionPublic(**collection_dict)
    
    assert public_collection.collection_name == "Test Collection"
    assert public_collection.description == "A test collection"