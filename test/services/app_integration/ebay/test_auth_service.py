import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.new_services.app_integration.ebay.auth import EbayAuthService

@pytest.fixture
def mock_auth_repo():
    return MagicMock()

@pytest.fixture
def mock_app_repo():
    return MagicMock()

@pytest.fixture
def mock_http_repo():
    repo = MagicMock()
    repo.request_auth_code = AsyncMock()
    return repo

@pytest.fixture
def ebay_auth_service(mock_auth_repo, mock_app_repo, mock_http_repo):
    return EbayAuthService(
        auth_repo=mock_auth_repo,
        app_repo=mock_app_repo,
        http_repo=mock_http_repo
    )

@pytest.fixture
def mock_settings():
    params = {
            "client_id": "app_id",
            "response_type": "response_type",
            "redirect_uri": "redirect_uri",
            "scope": "scope",
            "secret": "secret",
            "state": "state"
        }
    return params

@pytest.mark.asyncio
async def test_request_auth_code_success(ebay_auth_service, mock_http_repo, mock_settings):
    mock_http_repo.request_auth_code.return_value = None
    result = await ebay_auth_service.request_auth_code(mock_settings)
    assert result == None
    mock_http_repo.request_auth_code.assert_called_once_with(mock_settings)