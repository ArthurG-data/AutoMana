import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from backend.new_services.app_integration.ebay import app
from backend.schemas.external_marketplace.ebay.app import NewEbayApp, AssignScope

@pytest.fixture
def ebay_app_repository():
    repo = MagicMock()
    repo.add = AsyncMock()
    repo.assign_scope = AsyncMock()
    return repo

@pytest.fixture
def ebay_settings():
    return NewEbayApp(
        app_id="test_app_id",
        redirect_uri="https://example.com/redirect",
        response_type="code",
        secret="test_secret"
    )
@pytest.fixture
def assign_scope_data():
    return AssignScope(
        scope="test_scope",
        app_id="test_app_id",
        user_id="123e4567-e89b-12d3-a456-426614174000"  # Example UUID
    )

@pytest.mark.asyncio
async def test_register_app_success(ebay_app_repository, ebay_settings):
    ebay_app_repository.add.return_value = True
    result = await app.register_app(ebay_app_repository, ebay_settings)
    assert result is True
    ebay_app_repository.add.assert_called_once_with(
        (ebay_settings.app_id, ebay_settings.redirect_uri, ebay_settings.response_type, ebay_settings.secret)
    )

@pytest.mark.asyncio
async def test_register_app_failure(ebay_app_repository, ebay_settings):
    ebay_app_repository.add.return_value = False
    with pytest.raises(app.app_exception.EbayAppRegistrationException):
        await app.register_app(ebay_app_repository, ebay_settings)
    ebay_app_repository.add.assert_called_once_with(
        (ebay_settings.app_id, ebay_settings.redirect_uri, ebay_settings.response_type, ebay_settings.secret)
    )

@pytest.mark.asyncio
async def test_assign_scope_success(ebay_app_repository, assign_scope_data):
    ebay_app_repository.assign_scope.return_value = {"scope_id": "test_scope_id", "app_id": "test_app_id", "user_id": "test_user_id"}

    result = await app.assign_scope(ebay_app_repository, assign_scope_data)
    assert result == {"scope_id": "test_scope_id", "app_id": "test_app_id", "user_id": "test_user_id"}
    ebay_app_repository.assign_scope.assert_called_once_with(assign_scope_data.scope, assign_scope_data.app_id, assign_scope_data.user_id)

@pytest.mark.asyncio
async def test_assign_scope_failure(ebay_app_repository, assign_scope_data):
    ebay_app_repository.assign_scope.return_value = None
    with pytest.raises(app.app_exception.EbayScopeAssignmentException):
        await app.assign_scope(ebay_app_repository, assign_scope_data)
    ebay_app_repository.assign_scope.assert_called_once_with(assign_scope_data.scope, assign_scope_data.app_id, assign_scope_data.user_id)