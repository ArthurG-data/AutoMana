# tests/integration/services/ebay/conftest.py
from __future__ import annotations

import uuid

import asyncpg
import pytest_asyncio


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
async def seeded_db(db_pool):
    """Seed Sheoldred through the full FK chain and clean up after."""
    async with db_pool.acquire() as conn:
        # --- Reference rows (upsert — safe on repeated runs) ---
        set_type_id = await conn.fetchval(
            "INSERT INTO card_catalog.set_type_list_ref (set_type) VALUES ('expansion') "
            "ON CONFLICT (set_type) DO UPDATE SET set_type = EXCLUDED.set_type "
            "RETURNING set_type_id"
        )
        rarity_id = await conn.fetchval(
            "INSERT INTO card_catalog.rarities_ref (rarity_name) VALUES ('mythic') "
            "ON CONFLICT (rarity_name) DO UPDATE SET rarity_name = EXCLUDED.rarity_name "
            "RETURNING rarity_id"
        )
        border_id = await conn.fetchval(
            "INSERT INTO card_catalog.border_color_ref (border_color_name) VALUES ('black') "
            "ON CONFLICT (border_color_name) DO UPDATE SET border_color_name = EXCLUDED.border_color_name "
            "RETURNING border_color_id"
        )
        frame_id = await conn.fetchval(
            "INSERT INTO card_catalog.frames_ref (frame_year) VALUES ('2015') "
            "ON CONFLICT (frame_year) DO UPDATE SET frame_year = EXCLUDED.frame_year "
            "RETURNING frame_id"
        )
        layout_id = await conn.fetchval(
            "INSERT INTO card_catalog.layouts_ref (layout_name) VALUES ('normal') "
            "ON CONFLICT (layout_name) DO UPDATE SET layout_name = EXCLUDED.layout_name "
            "RETURNING layout_id"
        )

        # --- Unique card name per run (avoids UNIQUE conflict if fixture runs twice) ---
        card_name = f"Sheoldred, the Apocalypse [{uuid.uuid4().hex[:6].upper()}]"
        unique_card_id = await conn.fetchval(
            "INSERT INTO card_catalog.unique_cards_ref (card_name) VALUES ($1) "
            "RETURNING unique_card_id",
            card_name,
        )

        # --- Unique set per run ---
        set_code = "DMU" + uuid.uuid4().hex[:4].upper()
        set_id = await conn.fetchval(
            "INSERT INTO card_catalog.sets (set_name, set_code, set_type_id, released_at) "
            "VALUES ($1, $2, $3, '2022-09-09') RETURNING set_id",
            f"Dominaria United [{set_code}]", set_code, set_type_id,
        )

        card_version_id = await conn.fetchval(
            "INSERT INTO card_catalog.card_version "
            "(unique_card_id, set_id, collector_number, rarity_id, border_color_id, frame_id, layout_id) "
            "VALUES ($1, $2, '328', $3, $4, $5, $6) RETURNING card_version_id",
            unique_card_id, set_id, rarity_id, border_id, frame_id, layout_id,
        )

        # --- Pricing chain ---
        game_id = await conn.fetchval(
            "SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'"
        )
        product_id = await conn.fetchval(
            "INSERT INTO pricing.product_ref (game_id) VALUES ($1) RETURNING product_id",
            game_id,
        )
        await conn.execute(
            "INSERT INTO pricing.mtg_card_products (product_id, card_version_id) VALUES ($1, $2)",
            product_id, card_version_id,
        )

        # --- eBay source — looked up dynamically, never hardcoded ---
        ebay_source_id = await conn.fetchval(
            "SELECT source_id FROM pricing.price_source WHERE code = 'ebay'"
        )
        assert ebay_source_id is not None, "pricing.price_source has no 'ebay' row — check schema seed"
        source_product_id = await conn.fetchval(
            "INSERT INTO pricing.source_product (product_id, source_id) VALUES ($1, $2) "
            "ON CONFLICT (product_id, source_id) DO UPDATE SET product_id = EXCLUDED.product_id "
            "RETURNING source_product_id",
            product_id, ebay_source_id,
        )

        # --- English language_id ---
        language_id = await conn.fetchval(
            "SELECT language_id FROM card_catalog.language_ref WHERE language_code = 'en'"
        )
        assert language_id is not None, "card_catalog.language_ref has no 'en' row — check schema seed"

    yield {
        "card_name": card_name,
        "card_version_id": card_version_id,
        "product_id": product_id,
        "source_product_id": source_product_id,
        "language_id": language_id,
        "unique_card_id": unique_card_id,
        "set_id": set_id,
    }

    # --- Teardown: remove committed rows in reverse FK order ---
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE source_product_id = $1",
            source_product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.price_observation WHERE source_product_id = $1",
            source_product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.source_product WHERE source_product_id = $1",
            source_product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.mtg_card_products WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.product_ref WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM card_catalog.card_version WHERE card_version_id = $1",
            card_version_id,
        )
        await conn.execute(
            "DELETE FROM card_catalog.unique_cards_ref WHERE unique_card_id = $1",
            unique_card_id,
        )
        await conn.execute(
            "DELETE FROM card_catalog.sets WHERE set_id = $1", set_id
        )
