"""Unit tests for Shopify collection sync and repository bug fixes."""
import io
import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from automana.core.repositories.app_integration.shopify.market_repository import MarketRepository
from automana.core.repositories.app_integration.shopify.product_repository import ProductRepository


# ── Bug fix tests ─────────────────────────────────────────────────────────────

async def test_get_market_code_uses_pricing_schema():
    """get_market_code must query pricing.price_source, not bare price_source."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[{"source_id": 1728}])
    repo = MarketRepository(connection=mock_conn, executor=None)

    result = await repo.get_market_code("gg_sydney")

    assert result == 1728
    sql_used = mock_conn.fetch.call_args[0][0]
    assert "pricing.price_source" in sql_used, (
        f"Expected 'pricing.price_source' in query, got: {sql_used!r}"
    )


async def test_bulk_copy_prices_uses_pricing_schema():
    """bulk_copy_prices must copy into pricing.shopify_staging_raw, not bare name."""
    mock_conn = AsyncMock()
    mock_conn.copy_to_table = AsyncMock()
    mock_conn.execute = AsyncMock()
    repo = ProductRepository(connection=mock_conn, executor=None)
    df = pd.DataFrame({
        "product_id": [1], "date": ["2026-05-23"], "variation": ["Near Mint"],
        "price": [4.99], "scraped_at": ["2026-05-23"],
    })

    await repo.bulk_copy_prices(df)

    table_arg = mock_conn.copy_to_table.call_args.kwargs["table_name"]
    assert table_arg == "pricing.shopify_staging_raw", (
        f"Expected 'pricing.shopify_staging_raw', got: {table_arg!r}"
    )


async def test_bulk_copy_prices_does_not_commit():
    """bulk_copy_prices must not issue a manual COMMIT on the asyncpg connection."""
    mock_conn = AsyncMock()
    mock_conn.copy_to_table = AsyncMock()
    mock_conn.execute = AsyncMock()
    repo = ProductRepository(connection=mock_conn, executor=None)
    df = pd.DataFrame({
        "product_id": [1], "date": ["2026-05-23"], "variation": ["Near Mint"],
        "price": [4.99], "scraped_at": ["2026-05-23"],
    })

    await repo.bulk_copy_prices(df)

    for c in mock_conn.execute.call_args_list:
        sql = c[0][0] if c[0] else ""
        assert "COMMIT" not in sql.upper(), "bulk_copy_prices must not issue COMMIT"
