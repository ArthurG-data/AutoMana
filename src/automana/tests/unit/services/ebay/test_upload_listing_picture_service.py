import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID
from automana.core.services.app_integration.ebay.listings_write_service import (
    upload_listing_picture,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")

@pytest.fixture
def auth_repo():
    return AsyncMock()

@pytest.fixture
def selling_repo():
    repo = AsyncMock()
    repo.upload_picture = AsyncMock(return_value="https://i.ebayimg.com/test.jpg")
    return repo

@pytest.mark.asyncio
async def test_upload_returns_url(auth_repo, selling_repo):
    with patch(
        "automana.core.services.app_integration.ebay.listings_write_service.resolve_token",
        new=AsyncMock(return_value="access-token-123"),
    ):
        result = await upload_listing_picture(
            auth_repository=auth_repo,
            selling_repository=selling_repo,
            user_id=USER_ID,
            app_code="automana_au",
            file_bytes=b"img",
            content_type="image/jpeg",
        )
    assert result == {"url": "https://i.ebayimg.com/test.jpg"}
    selling_repo.upload_picture.assert_awaited_once_with(
        token="access-token-123",
        file_bytes=b"img",
        content_type="image/jpeg",
    )

@pytest.mark.asyncio
async def test_upload_propagates_repository_error(auth_repo, selling_repo):
    selling_repo.upload_picture = AsyncMock(side_effect=ValueError("eBay upload rejected"))
    with patch(
        "automana.core.services.app_integration.ebay.listings_write_service.resolve_token",
        new=AsyncMock(return_value="token"),
    ):
        with pytest.raises(ValueError, match="eBay upload rejected"):
            await upload_listing_picture(
                auth_repository=auth_repo,
                selling_repository=selling_repo,
                user_id=USER_ID,
                app_code="automana_au",
                file_bytes=b"img",
                content_type="image/jpeg",
            )
