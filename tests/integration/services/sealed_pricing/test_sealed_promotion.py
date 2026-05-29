"""Integration tests for sealed product pricing schema and promotion procedure."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


async def test_sealed_products_table_exists(db_pool):
    """pricing.sealed_products must exist in the test container."""
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'pricing' AND table_name = 'sealed_products'"
            ")"
        )
    assert exists, "pricing.sealed_products table does not exist — check 12_sealed_pricing.sql"


async def test_sealed_price_latest_table_exists(db_pool):
    """pricing.sealed_price_latest must exist in the test container."""
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'pricing' AND table_name = 'sealed_price_latest'"
            ")"
        )
    assert exists, "pricing.sealed_price_latest table does not exist — check 12_sealed_pricing.sql"


async def test_staged_sealed_row_promotes_to_price_observation(db_pool, sealed_db):
    """One staged row (tcgplayer/retail/USD) must land in price_observation after CALL."""
    sealed_uuid = sealed_db["sealed_uuid"]
    product_id = sealed_db["product_id"]

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pricing.mtgjson_sealed_prices_staging "
            "(sealed_uuid, price_source, price_type, currency, price_value, price_date) "
            "VALUES ($1, 'tcgplayer', 'retail', 'USD', 99.99, '2026-03-01')",
            sealed_uuid,
        )

    async with db_pool.acquire() as conn:
        await conn.execute(
            "CALL pricing.load_price_observation_from_mtgjson_sealed_staging()"
        )

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM pricing.price_observation "
            "WHERE source_product_id IN "
            "(SELECT source_product_id FROM pricing.source_product WHERE product_id = $1)",
            product_id,
        )

    assert count == 1, (
        f"Expected 1 row in price_observation for product_id={product_id}, got {count}"
    )


async def test_snapshot_updated_after_promotion(db_pool, sealed_db):
    """sealed_price_latest must have list_avg_cents == 8999 after promoting price_value=89.99."""
    sealed_uuid = sealed_db["sealed_uuid"]
    product_id = sealed_db["product_id"]

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pricing.mtgjson_sealed_prices_staging "
            "(sealed_uuid, price_source, price_type, currency, price_value, price_date) "
            "VALUES ($1, 'tcgplayer', 'retail', 'USD', 89.99, '2026-03-02')",
            sealed_uuid,
        )

    async with db_pool.acquire() as conn:
        await conn.execute(
            "CALL pricing.load_price_observation_from_mtgjson_sealed_staging()"
        )

    async with db_pool.acquire() as conn:
        list_avg_cents = await conn.fetchval(
            "SELECT list_avg_cents FROM pricing.sealed_price_latest "
            "WHERE product_id = $1",
            product_id,
        )

    assert list_avg_cents == 8999, (
        f"Expected list_avg_cents=8999, got {list_avg_cents}"
    )
