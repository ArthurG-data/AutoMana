"""Shared fixtures for sealed pricing integration tests."""
from __future__ import annotations

import uuid
from datetime import date

import asyncpg
import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration]

_PRICE_DATE = date(2026, 3, 1)


@pytest_asyncio.fixture(scope="function")
async def db_pool(timescale_container, _test_env, db_migrations_applied):
    host = timescale_container.get_container_host_ip()
    port = timescale_container.get_exposed_port(5432)
    pool = await asyncpg.create_pool(
        host=host,
        port=int(port),
        user="automana_test",
        password="test_password",
        database="automana_test",
        min_size=1,
        max_size=3,
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def sealed_db(db_pool):
    """Seed minimum rows for sealed pricing tests; clean up after."""
    sealed_uuid = f"sealed-{uuid.uuid4().hex}"
    set_code = uuid.uuid4().hex[:6].upper()

    async with db_pool.acquire() as conn:
        set_type_id = await conn.fetchval(
            "INSERT INTO card_catalog.set_type_list_ref (set_type) VALUES ('draft_innovation') "
            "ON CONFLICT (set_type) DO UPDATE SET set_type = EXCLUDED.set_type "
            "RETURNING set_type_id"
        )
        set_id = await conn.fetchval(
            "INSERT INTO card_catalog.sets (set_name, set_code, set_type_id, released_at) "
            "VALUES ($1, $2, $3, '2026-01-01') RETURNING set_id",
            f"Test Set {set_code}", set_code, set_type_id,
        )
        game_id = await conn.fetchval(
            "SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'"
        )
        product_id = await conn.fetchval(
            "INSERT INTO pricing.product_ref (game_id) VALUES ($1) RETURNING product_id",
            game_id,
        )
        await conn.execute(
            "INSERT INTO pricing.sealed_products "
            "(product_id, set_id, name, product_type, mtgjson_uuid) "
            "VALUES ($1, $2, $3, $4, $5)",
            product_id, set_id,
            f"Test Booster Box {set_code}", "booster_box", sealed_uuid,
        )
        await conn.execute("DELETE FROM pricing.mtgjson_sealed_prices_staging")

    yield {
        "sealed_uuid": sealed_uuid,
        "product_id": product_id,
        "set_id": set_id,
        "set_code": set_code,
    }

    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.sealed_price_latest WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.price_observation WHERE source_product_id IN "
            "(SELECT source_product_id FROM pricing.source_product WHERE product_id = $1)",
            product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.source_product WHERE product_id = $1", product_id
        )
        await conn.execute("DELETE FROM pricing.mtgjson_sealed_prices_staging")
        await conn.execute(
            "DELETE FROM pricing.sealed_products WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.product_ref WHERE product_id = $1", product_id
        )
        await conn.execute("DELETE FROM card_catalog.sets WHERE set_id = $1", set_id)
