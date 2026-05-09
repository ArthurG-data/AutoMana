import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository

MOCK_SUCCESS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<UploadSiteHostedPicturesResponse xmlns="urn:ebay:apis:eBLBaseComponents">
  <Timestamp>2026-05-09T00:00:00.000Z</Timestamp>
  <Ack>Success</Ack>
  <SiteHostedPictureDetails>
    <FullURL>https://i.ebayimg.com/00/s/test/image.jpg</FullURL>
  </SiteHostedPictureDetails>
</UploadSiteHostedPicturesResponse>"""

MOCK_FAILURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<UploadSiteHostedPicturesResponse xmlns="urn:ebay:apis:eBLBaseComponents">
  <Ack>Failure</Ack>
  <Errors>
    <ShortMessage>Invalid image</ShortMessage>
  </Errors>
</UploadSiteHostedPicturesResponse>"""

@pytest.fixture
def repo():
    return EbaySellingRepository(environment="sandbox")

@pytest.mark.asyncio
async def test_upload_picture_returns_url(repo):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = MOCK_SUCCESS_XML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        url = await repo.upload_picture(
            token="test-token",
            file_bytes=b"fake-image",
            content_type="image/jpeg",
        )

    assert url == "https://i.ebayimg.com/00/s/test/image.jpg"

@pytest.mark.asyncio
async def test_upload_picture_passes_correct_call_name(repo):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = MOCK_SUCCESS_XML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await repo.upload_picture(
            token="test-token",
            file_bytes=b"fake-image",
            content_type="image/jpeg",
        )

    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"]["X-EBAY-API-CALL-NAME"] == "UploadSiteHostedPictures"

@pytest.mark.asyncio
async def test_upload_picture_raises_on_failure_ack(repo):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = MOCK_FAILURE_XML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="eBay upload rejected"):
            await repo.upload_picture(
                token="test-token",
                file_bytes=b"fake-image",
                content_type="image/jpeg",
            )
