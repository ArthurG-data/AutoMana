import pandas as pd
import pytest
from automana.core.services.app_integration.shopify.data_staging_service import _dedupe_batch


class TestDedupeWithCollectionTier:
    def test_instock_tier_wins_over_set_tier_when_prices_differ(self):
        df = pd.DataFrame([
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 4.50, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 0},
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 5.00, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 1},
        ])
        result = _dedupe_batch(df)
        assert len(result) == 1
        assert result.iloc[0]["price"] == 5.00

    def test_set_tier_wins_when_only_set_present(self):
        df = pd.DataFrame([
            {"product_id": 2, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 3.00, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 0},
        ])
        result = _dedupe_batch(df)
        assert len(result) == 1
        assert result.iloc[0]["price"] == 3.00

    def test_collection_tier_column_is_dropped_from_result(self):
        df = pd.DataFrame([
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 5.00, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 1},
        ])
        result = _dedupe_batch(df)
        assert "collection_tier" not in result.columns

    def test_no_collection_tier_column_still_dedupes(self):
        """Backwards compatibility: existing parquet files without collection_tier still work."""
        df = pd.DataFrame([
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 4.00, "scraped_at": pd.Timestamp("2026-05-01 10:00")},
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 4.50, "scraped_at": pd.Timestamp("2026-05-01 11:00")},
        ])
        result = _dedupe_batch(df)
        assert len(result) == 1
