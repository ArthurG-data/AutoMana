import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

@pytest.fixture
def mock_auth_repository():
    """Mock authentication repository"""
    repo = AsyncMock()
    # Setup common mock methods
    repo.validate_credentials.return_value = {
        "unique_id": uuid4(),
        "username": "testuser",
        "email": "test@example.com",
        "role": "user",
        "disabled": False
    }
    return repo

@pytest.fixture
def mock_session_repository():
    """Mock session repository"""
    repo = AsyncMock()
    # Setup common mock methods
    return repo

@pytest.fixture
def mock_token_repository():
    """Mock token repository"""
    repo = AsyncMock()
    # Setup common mock methods
    return repo

@pytest.fixture
def mock_collection_repository():
    """Mock collection repository"""
    repo = AsyncMock()
    # Setup common mock methods
    return repo

@pytest.fixture
def test_user():
    """Test user data"""
    return {
        "unique_id": uuid4(),
        "username": "testuser",
        "email": "test@example.com",
        "role": "user",
        "disabled": False
    }

@pytest.fixture
def test_session_data():
    """Test session data"""
    return {
        "session_id": uuid4(),
        "user_id": uuid4(),
        "token_id": uuid4(),
        "refresh_token": "test_refresh_token",
        "ip_address": "127.0.0.1",
        "user_agent": "Test Browser"
    }