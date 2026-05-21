import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import (
    EbayAuthRepository,
)

USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def repo():
    conn = MagicMock()
    with patch("automana.core.repositories.app_integration.ebay.auth_repository.get_pgp_key", return_value="key"):
        r = EbayAuthRepository(connection=conn, executor=None)
    r.execute_query = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_get_active_app_code_users_returns_list(repo):
    repo.execute_query.return_value = [
        {"user_id": USER_ID, "app_code": "my-app"},
    ]
    result = await repo.get_active_app_code_users()
    assert result == [{"user_id": USER_ID, "app_code": "my-app"}]
    repo.execute_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_active_app_code_users_empty(repo):
    repo.execute_query.return_value = []
    result = await repo.get_active_app_code_users()
    assert result == []
