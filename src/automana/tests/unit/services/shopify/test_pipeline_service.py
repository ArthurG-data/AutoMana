import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestFetchCollections:
    @pytest.mark.asyncio
    async def test_fetches_sitemap_and_upserts_handles(self):
        from automana.core.services.app_integration.shopify.pipeline_service import fetch_collections

        pipeline_repo = AsyncMock()
        pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=[
            {"market_id": 1, "name": "GG Brisbane", "api_url": "https://tcg.goodgames.com.au",
             "source_id": 1727, "source_code": "gg_brisbane"},
        ])
        collection_repo = AsyncMock()
        ops_repo = AsyncMock()
        ops_repo.__aenter__ = AsyncMock(return_value=ops_repo)
        ops_repo.__aexit__ = AsyncMock(return_value=False)
        api_repo = AsyncMock()
        api_repo.get_sitemap_collection_handles = AsyncMock(
            return_value=["magic-the-gathering-singles-in-stock", "bloomburrow-singles"]
        )

        with patch(
            "automana.core.services.app_integration.shopify.pipeline_service.track_step",
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)),
        ):
            result = await fetch_collections(
                shopify_pipeline_repository=pipeline_repo,
                collection_repository=collection_repo,
                ops_repository=ops_repo,
                shopify_api_repository=api_repo,
                ingestion_run_id=42,
            )

        api_repo.get_sitemap_collection_handles.assert_awaited_once_with("https://tcg.goodgames.com.au")
        collection_repo.add_many.assert_awaited_once()
        rows_passed = collection_repo.add_many.call_args[0][0]
        assert len(rows_passed) == 2
        assert any(r.name == "magic-the-gathering-singles-in-stock" for r in rows_passed)
        assert result["collections_synced"] == 2

    @pytest.mark.asyncio
    async def test_no_active_markets_returns_zero(self):
        from automana.core.services.app_integration.shopify.pipeline_service import fetch_collections

        pipeline_repo = AsyncMock()
        pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=[])
        collection_repo = AsyncMock()

        result = await fetch_collections(
            shopify_pipeline_repository=pipeline_repo,
            collection_repository=collection_repo,
            ops_repository=AsyncMock(),
            shopify_api_repository=AsyncMock(),
            ingestion_run_id=None,
        )

        collection_repo.add_many.assert_not_awaited()
        assert result["collections_synced"] == 0
