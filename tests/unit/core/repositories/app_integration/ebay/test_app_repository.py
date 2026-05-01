import pytest
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository


@pytest.fixture
def repo():
    conn = MagicMock()
    executor = MagicMock()
    r = EbayAppRepository(connection=conn, executor=executor)
    r.execute_query = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_update_redirect_uri_returns_true_on_success(repo):
    repo.execute_query.return_value = [{"app_code": "my-app"}]
    result = await repo.update_redirect_uri("my-app", "https://automana.duckdns.org/api/integrations/ebay/auth/callback")
    assert result is True


@pytest.mark.asyncio
async def test_update_redirect_uri_returns_false_when_app_not_found(repo):
    repo.execute_query.return_value = []
    result = await repo.update_redirect_uri("unknown-app", "https://automana.duckdns.org/api/integrations/ebay/auth/callback")
    assert result is False


@pytest.mark.asyncio
async def test_update_redirect_uri_passes_correct_args(repo):
    repo.execute_query.return_value = [{"app_code": "my-app"}]
    url = "https://automana.duckdns.org/api/integrations/ebay/auth/callback"
    await repo.update_redirect_uri("my-app", url)
    repo.execute_query.assert_called_once()
    call_args = repo.execute_query.call_args
    assert call_args[0][1] == (url, "my-app")
