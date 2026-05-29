"""Integration tests for the sealed pricing API endpoints."""
from __future__ import annotations

import uuid
from datetime import date

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(loop_scope="session", scope="module")
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


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def sealed_api_seed(db_pool):
    """Seed one sealed product with a price row in sealed_price_latest."""
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
            f"API Test Sealed Set {set_code}", set_code, set_type_id,
        )
        game_id = await conn.fetchval(
            "SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'"
        )
        language_id = await conn.fetchval(
            "SELECT language_id FROM card_catalog.language_ref WHERE language_code = 'en'"
        )
        sealed_type_id = await conn.fetchval(
            "SELECT sealed_type_id FROM card_catalog.sealed_type_ref WHERE type_code = 'booster_box'"
        )

        sealed_product_id = await conn.fetchval(
            "INSERT INTO card_catalog.sealed_product "
            "(set_id, game_id, sealed_type_id, language_id, name) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING sealed_product_id",
            set_id, game_id, sealed_type_id, language_id,
            f"API Test Booster Box {set_code}",
        )

        uuid_ref_id = await conn.fetchval(
            "SELECT sealed_identifier_ref_id FROM card_catalog.sealed_identifier_ref "
            "WHERE identifier_name = 'mtgjson_uuid'"
        )
        await conn.execute(
            "INSERT INTO card_catalog.sealed_external_identifier "
            "(sealed_identifier_ref_id, sealed_product_id, value) VALUES ($1, $2, $3)",
            uuid_ref_id, sealed_product_id, sealed_uuid,
        )

        product_id = await conn.fetchval(
            "INSERT INTO pricing.product_ref (game_id) VALUES ($1) RETURNING product_id",
            game_id,
        )
        await conn.execute(
            "INSERT INTO pricing.mtg_sealed_products (product_id, sealed_product_id) "
            "VALUES ($1, $2)",
            product_id, sealed_product_id,
        )

        await conn.execute(
            "INSERT INTO pricing.price_source (code, name, currency_code) "
            "VALUES ('tcg', 'tcgplayer', 'USD') ON CONFLICT (code) DO NOTHING"
        )
        tcg_source_id = await conn.fetchval(
            "SELECT source_id FROM pricing.price_source WHERE code = 'tcg'"
        )
        await conn.execute(
            "INSERT INTO pricing.transaction_type (transaction_type_code) "
            "VALUES ('sell') ON CONFLICT (transaction_type_code) DO NOTHING"
        )
        sell_type_id = await conn.fetchval(
            "SELECT transaction_type_id FROM pricing.transaction_type "
            "WHERE transaction_type_code = 'sell'"
        )
        await conn.execute(
            "INSERT INTO pricing.sealed_price_latest "
            "(product_id, source_id, transaction_type_id, price_date, list_avg_cents) "
            "VALUES ($1, $2, $3, '2026-03-01', 9999)",
            product_id, tcg_source_id, sell_type_id,
        )

    yield {
        "sealed_uuid":       sealed_uuid,
        "sealed_product_id": sealed_product_id,
        "product_id":        product_id,
        "set_id":            set_id,
        "set_code":          set_code,
    }

    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.sealed_price_latest WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.mtg_sealed_products WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.product_ref WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM card_catalog.sealed_product WHERE sealed_product_id = $1",
            sealed_product_id,
        )
        await conn.execute("DELETE FROM card_catalog.sets WHERE set_id = $1", set_id)


async def test_get_sealed_prices_by_set_returns_200(client, sealed_api_seed):
    set_code = sealed_api_seed["set_code"]
    response = await client.get(f"/api/catalog/mtg/sealed/{set_code}/prices")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["set_code"] == set_code
    prices = body["prices"]
    assert len(prices) == 1, f"Expected 1 price row, got {len(prices)}"
    row = prices[0]
    assert row["type_code"] == "booster_box"
    assert row["list_avg_cents"] == 9999
    assert row["mtgjson_uuid"] == sealed_api_seed["sealed_uuid"]


async def test_get_sealed_prices_unknown_set_returns_404(client):
    response = await client.get("/api/catalog/mtg/sealed/ZZZNOPE/prices")
    assert response.status_code == 404, (
        f"Expected 404, got {response.status_code}: {response.text}"
    )
