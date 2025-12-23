import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from backend.new_services.user_management.user_service import (
    create_user,
    get_user_by_id,
    update_user,
    delete_user,
    get_all_users
)
from backend.schemas.user_management.user import BaseUser, UserPublic
from backend.utils.auth.auth import get_hash_password

class TestUserService:
    
    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_user_repository, sample_user_data):
        """Test successful user creation"""
        # Arrange
        expected_user_id = uuid4()
        mock_user_repository.add.return_value = [{"unique_id": str(expected_user_id)}]
        mock_user_repository.get_by_username.return_value = None  # Username not taken
        mock_user_repository.get_by_email.return_value = None     # Email not taken
        
        # Act
        result = await create_user(
            mock_user_repository,
            username=sample_user_data["username"],
            email=sample_user_data["email"],
            fullname=sample_user_data["fullname"],
            password=sample_user_data["password"]
        )
        
        # Assert
        assert result is not None
        assert "unique_id" in result
        mock_user_repository.get_by_username.assert_called_once_with(sample_user_data["username"])
        mock_user_repository.get_by_email.assert_called_once_with(sample_user_data["email"])
        mock_user_repository.add.assert_called_once()
        
        # Verify password was hashed
        call_args = mock_user_repository.add.call_args[0][0]
        assert call_args["password"] != sample_user_data["password"]  # Should be hashed
    
    @pytest.mark.asyncio
    async def test_create_user_username_exists(self, mock_user_repository, sample_user_data):
        """Test user creation fails when username already exists"""
        # Arrange
        mock_user_repository.get_by_username.return_value = {"username": sample_user_data["username"]}
        
        # Act
        result = await create_user(
            mock_user_repository,
            username=sample_user_data["username"],
            email=sample_user_data["email"],
            fullname=sample_user_data["fullname"],
            password=sample_user_data["password"]
        )
        
        # Assert
        assert result is None
        mock_user_repository.add.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_create_user_email_exists(self, mock_user_repository, sample_user_data):
        """Test user creation fails when email already exists"""
        # Arrange
        mock_user_repository.get_by_username.return_value = None
        mock_user_repository.get_by_email.return_value = {"email": sample_user_data["email"]}
        
        # Act
        result = await create_user(
            mock_user_repository,
            username=sample_user_data["username"],
            email=sample_user_data["email"],
            fullname=sample_user_data["fullname"],
            password=sample_user_data["password"]
        )
        
        # Assert
        assert result is None
        mock_user_repository.add.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self, mock_user_repository):
        """Test successful user retrieval by ID"""
        # Arrange
        user_id = uuid4()
        expected_user = {
            "unique_id": str(user_id),
            "username": "testuser",
            "email": "test@example.com",
            "fullname": "Test User",
            "is_active": True
        }
        mock_user_repository.get_by_id.return_value = expected_user
        
        # Act
        result = await get_user_by_id(mock_user_repository, user_id)
        
        # Assert
        assert result == expected_user
        mock_user_repository.get_by_id.assert_called_once_with(user_id)
    
    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, mock_user_repository):
        """Test user retrieval when user doesn't exist"""
        # Arrange
        user_id = uuid4()
        mock_user_repository.get_by_id.return_value = None
        
        # Act
        result = await get_user_by_id(mock_user_repository, user_id)
        
        # Assert
        assert result is None
        mock_user_repository.get_by_id.assert_called_once_with(user_id)
    
    @pytest.mark.asyncio
    async def test_update_user_success(self, mock_user_repository):
        """Test successful user update"""
        # Arrange
        user_id = uuid4()
        updated_data = {
            "unique_id": str(user_id),
            "username": "updateduser",
            "email": "updated@example.com",
            "fullname": "Updated User"
        }
        mock_user_repository.update.return_value = updated_data
        
        # Act
        result = await update_user(
            mock_user_repository,
            user_id,
            username="updateduser",
            email="updated@example.com",
            fullname="Updated User"
        )
        
        # Assert
        assert result == updated_data
        mock_user_repository.update.assert_called_once_with(
            user_id, "updateduser", "updated@example.com", "Updated User"
        )
    
    @pytest.mark.asyncio
    async def test_delete_user_success(self, mock_user_repository):
        """Test successful user deletion"""
        # Arrange
        user_id = uuid4()
        mock_user_repository.delete.return_value = True
        
        # Act
        result = await delete_user(mock_user_repository, user_id)
        
        # Assert
        assert result is True
        mock_user_repository.delete.assert_called_once_with(user_id)
    
    @pytest.mark.asyncio
    async def test_get_all_users_success(self, mock_user_repository):
        """Test successful retrieval of all users"""
        # Arrange
        expected_users = [
            {"unique_id": str(uuid4()), "username": "user1", "email": "user1@example.com"},
            {"unique_id": str(uuid4()), "username": "user2", "email": "user2@example.com"}
        ]
        mock_user_repository.get_all.return_value = expected_users
        
        # Act
        result = await get_all_users(mock_user_repository)
        
        # Assert
        assert result == expected_users
        mock_user_repository.get_all.assert_called_once()