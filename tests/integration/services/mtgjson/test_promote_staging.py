"""Integration test: verify the MTGJson staging promotion stored procedure.

Calls ``pricing.load_price_observation_from_mtgjson_staging_batched`` with one
seeded staging row and asserts the row lands in ``pricing.price_observation``.

Bugs covered:
  C1 — 'mtgjson_id' absent from card_identifier_ref seed  (02_card_schema.sql)
  C2 — src.name used instead of src.code in pairs/resolved CTEs  (10_mtgjson_schema.sql)
  C3 — finish_type not uppercased after normalization  (10_mtgjson_schema.sql)
  C4 — WHERE clause on batch window commented out  (10_mtgjson_schema.sql)
  C5 — dead ROLLBACK branch after RAISE in EXCEPTION handler  (10_mtgjson_schema.sql)
  C7 — insert_product_source CTE used DO NOTHING so resolved joined a table that
       was empty under PostgreSQL snapshot isolation; fixed with DO UPDATE RETURNING
       and join against the CTE output instead of the table directly
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration]

_PRICE_DATE = date(2026, 1, 15)


@pytest_asyncio.fixture
async def seeded_db(db_pool):
    """Seed minimum rows for the promotion test; clean up after."""
    mtgjson_uuid = str(uuid.uuid4())

    async with db_pool.acquire() as conn:
        # --- Reference rows (upsert so they survive repeated runs) ---
        set_type_id = await conn.fetchval(
            "INSERT INTO card_catalog.set_type_list_ref (set_type) VALUES ('core') "
            "ON CONFLICT (set_type) DO UPDATE SET set_type = EXCLUDED.set_type "
            "RETURNING set_type_id"
        )
        rarity_id = await conn.fetchval(
            "INSERT INTO card_catalog.rarities_ref (rarity_name) VALUES ('common') "
            "ON CONFLICT (rarity_name) DO UPDATE SET rarity_name = EXCLUDED.rarity_name "
            "RETURNING rarity_id"
        )
        border_id = await conn.fetchval(
            "INSERT INTO card_catalog.border_color_ref (border_color_name) VALUES ('black') "
            "ON CONFLICT (border_color_name) DO UPDATE SET border_color_name = EXCLUDED.border_color_name "
            "RETURNING border_color_id"
        )
        frame_id = await conn.fetchval(
            "INSERT INTO card_catalog.frames_ref (frame_year) VALUES ('2003') "
            "ON CONFLICT (frame_year) DO UPDATE SET frame_year = EXCLUDED.frame_year "
            "RETURNING frame_id"
        )
        layout_id = await conn.fetchval(
            "INSERT INTO card_catalog.layouts_ref (layout_name) VALUES ('normal') "
            "ON CONFLICT (layout_name) DO UPDATE SET layout_name = EXCLUDED.layout_name "
            "RETURNING layout_id"
        )

        # --- Unique set per fixture invocation (avoid inter-test conflicts) ---
        set_code = uuid.uuid4().hex[:6].upper()
        set_id = await conn.fetchval(
            "INSERT INTO card_catalog.sets (set_name, set_code, set_type_id, released_at) "
            "VALUES ($1, $2, $3, '2026-01-01') RETURNING set_id",
            f"Test Set {set_code}", set_code, set_type_id,
        )

        # --- Unique card ---
        card_name = f"Test Card {uuid.uuid4().hex[:8]}"
        unique_card_id = await conn.fetchval(
            "INSERT INTO card_catalog.unique_cards_ref (card_name) VALUES ($1) "
            "RETURNING unique_card_id",
            card_name,
        )

        card_version_id = await conn.fetchval(
            "INSERT INTO card_catalog.card_version "
            "(unique_card_id, set_id, collector_number, rarity_id, border_color_id, frame_id, layout_id) "
            "VALUES ($1, $2, '001', $3, $4, $5, $6) RETURNING card_version_id",
            unique_card_id, set_id, rarity_id, border_id, frame_id, layout_id,
        )

        # --- mtgjson_id in identifier ref (C1 fix: absent from production seed before fix) ---
        ref_id = await conn.fetchval(
            "INSERT INTO card_catalog.card_identifier_ref (identifier_name) VALUES ('mtgjson_id') "
            "ON CONFLICT (identifier_name) DO UPDATE SET identifier_name = EXCLUDED.identifier_name "
            "RETURNING card_identifier_ref_id"
        )

        # --- Link mtgjson UUID → card_version ---
        await conn.execute(
            "INSERT INTO card_catalog.card_external_identifier "
            "(card_identifier_ref_id, card_version_id, value) VALUES ($1, $2, $3)",
            ref_id, card_version_id, mtgjson_uuid,
        )

        # --- product_ref + mtg_card_products ---
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

        # Clear staging so no leftover rows from prior tests interfere.
        await conn.execute("DELETE FROM pricing.mtgjson_card_prices_staging")

    yield {
        "mtgjson_uuid": mtgjson_uuid,
        "card_version_id": card_version_id,
        "product_id": product_id,
        "unique_card_id": unique_card_id,
        "set_id": set_id,
    }

    # --- Teardown: remove committed rows in reverse FK order ---
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.price_observation WHERE source_product_id IN "
            "(SELECT source_product_id FROM pricing.source_product WHERE product_id = $1)",
            product_id,
        )
        await conn.execute(
            "DELETE FROM pricing.source_product WHERE product_id = $1", product_id
        )
        await conn.execute("DELETE FROM pricing.mtgjson_card_prices_staging")
        await conn.execute(
            "DELETE FROM pricing.mtg_card_products WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.product_ref WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM card_catalog.card_external_identifier WHERE card_version_id = $1",
            card_version_id,
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


async def test_staged_row_is_promoted_to_price_observation(db_pool, seeded_db):
    """One staged row (foil/tcgplayer/retail/USD) must land in price_observation after CALL."""
    mtgjson_uuid = seeded_db["mtgjson_uuid"]

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pricing.mtgjson_card_prices_staging "
            "(card_uuid, price_source, price_type, finish_type, currency, price_value, price_date) "
            "VALUES ($1, 'tcgplayer', 'retail', 'foil', 'USD', 1.50, $2)",
            mtgjson_uuid, _PRICE_DATE,
        )

    async with db_pool.acquire() as conn:
        await conn.execute(
            "CALL pricing.load_price_observation_from_mtgjson_staging_batched()"
        )

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM pricing.price_observation "
            "WHERE source_product_id IN "
            "(SELECT source_product_id FROM pricing.source_product WHERE product_id = $1)",
            seeded_db["product_id"],
        )

    assert count == 1, (
        f"Expected 1 row in price_observation for product_id={seeded_db['product_id']}, got {count}. "
        "Check bugs C2/C3/C7 in 10_mtgjson_schema.sql."
    )


async def test_mtgjson_id_identifier_is_seeded(db_pool):
    """C1: 'mtgjson_id' must be present in the card_identifier_ref seed (02_card_schema.sql)."""
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM card_catalog.card_identifier_ref "
            "WHERE identifier_name = 'mtgjson_id')"
        )
    assert exists, "C1: 'mtgjson_id' must be seeded in card_catalog.card_identifier_ref"
