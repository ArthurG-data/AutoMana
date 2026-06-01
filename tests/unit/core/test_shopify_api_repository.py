import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from automana.core.repositories.app_integration.shopify.ApiShopify_repository import ShopifyAPIRepository


@pytest.fixture
def repo():
    return ShopifyAPIRepository()


def _mock_response(text="", json_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


class TestGetCollectionProductsPage:
    @pytest.mark.asyncio
    async def test_returns_products_list(self, repo):
        products = [{"id": 1, "title": "Ragavan"}, {"id": 2, "title": "Bolt"}]
        mock_resp = _mock_response(json_data={"products": products})

        with patch.object(repo, "send", new=AsyncMock(return_value=mock_resp)):
            result = await repo.get_collection_products_page(
                "https://tcg.goodgames.com.au", "bloomburrow-singles", since_id=0
            )

        assert result == products

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_products(self, repo):
        mock_resp = _mock_response(json_data={"products": []})

        with patch.object(repo, "send", new=AsyncMock(return_value=mock_resp)):
            result = await repo.get_collection_products_page(
                "https://tcg.goodgames.com.au", "bloomburrow-singles", since_id=999
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_passes_since_id_and_limit_as_params(self, repo):
        mock_resp = _mock_response(json_data={"products": []})
        send_mock = AsyncMock(return_value=mock_resp)

        with patch.object(repo, "send", new=send_mock):
            await repo.get_collection_products_page(
                "https://tcg.goodgames.com.au", "magic-the-gathering-singles-in-stock",
                since_id=12345, limit=250
            )

        call_kwargs = send_mock.call_args
        assert call_kwargs.kwargs["params"] == {"limit": 250, "since_id": 12345}


class TestGetSitemapCollectionHandles:
    SITEMAP_XML = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://tcg.goodgames.com.au/sitemap_collections_1.xml?from=1&amp;to=2</loc></sitemap>
    </sitemapindex>"""

    COLLECTIONS_XML = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://tcg.goodgames.com.au/collections/bloomburrow-singles</loc></url>
      <url><loc>https://tcg.goodgames.com.au/collections/magic-the-gathering-singles-in-stock</loc></url>
      <url><loc>https://tcg.goodgames.com.au/collections/bloomburrow-singles</loc></url>
    </urlset>"""

    @pytest.mark.asyncio
    async def test_returns_deduplicated_handles(self, repo):
        sitemap_resp = _mock_response(text=self.SITEMAP_XML)
        collections_resp = _mock_response(text=self.COLLECTIONS_XML)
        send_mock = AsyncMock(side_effect=[sitemap_resp, collections_resp])

        with patch.object(repo, "send", new=send_mock):
            async with repo:
                handles = await repo.get_sitemap_collection_handles("https://tcg.goodgames.com.au")

        assert set(handles) == {"bloomburrow-singles", "magic-the-gathering-singles-in-stock"}
        assert len(handles) == 2  # deduped

    @pytest.mark.asyncio
    async def test_handles_multiple_sitemap_pages(self, repo):
        sitemap_two_pages = """<?xml version="1.0"?>
        <sitemapindex>
          <sitemap><loc>https://tcg.goodgames.com.au/sitemap_collections_1.xml</loc></sitemap>
          <sitemap><loc>https://tcg.goodgames.com.au/sitemap_collections_2.xml</loc></sitemap>
        </sitemapindex>"""
        page1 = _mock_response(text='<urlset><url><loc>https://x.com/collections/alpha</loc></url></urlset>')
        page2 = _mock_response(text='<urlset><url><loc>https://x.com/collections/beta</loc></url></urlset>')
        send_mock = AsyncMock(side_effect=[_mock_response(text=sitemap_two_pages), page1, page2])

        with patch.object(repo, "send", new=send_mock):
            async with repo:
                handles = await repo.get_sitemap_collection_handles("https://x.com")

        assert set(handles) == {"alpha", "beta"}
