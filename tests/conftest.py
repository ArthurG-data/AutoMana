"""
Top-level shared fixtures for all test domains.
Repository mocks are AsyncMock so `await repo.method()` works without extra setup.
Add method-specific return values in the test body, not here.
"""
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_ops_repository():
    return AsyncMock()


@pytest.fixture
def mock_session_repository():
    return AsyncMock()


@pytest.fixture
def mock_user_repository():
    return AsyncMock()


@pytest.fixture
def mock_auth_repository():
    return AsyncMock()


@pytest.fixture
def mock_selling_repository():
    return AsyncMock()
