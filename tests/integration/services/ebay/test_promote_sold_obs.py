"""Integration tests: eBay sold price staging → price_observation.

Closes GitHub issue #64 — [Feature]: Save results to DB.

test_staged_row_is_promoted_to_price_observation:
    Deterministic. Seeds one row in ebay_scraped_sold, calls promote_sold_obs
    with real asyncpg repos, asserts the row lands in price_observation.
    No network. Runs in CI.

test_live_sheoldred_pipeline:
    Live smoke test. Calls the real eBay Finding API for Sheoldred DMU,
    inserts valid sold items, promotes them, and prints a human-readable
    price summary. Requires EBAY_APP_ID env var. Excluded from CI.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration]

_YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)


async def test_staged_row_is_promoted_to_price_observation(db_pool, seeded_db):
    """One staged USD/FOIL/NM row must appear in price_observation after promote_sold_obs."""
    from automana.core.repositories.app_integration.ebay.sales_repository import (
        EbaySalesRepository,
    )
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
        EbayScrapeSoldRepository,
    )
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
    from automana.core.services.app_integration.ebay.promote_sold_obs_service import (
        promote_sold_obs,
    )

    source_product_id = seeded_db["source_product_id"]
    language_id = seeded_db["language_id"]

    # Step 1: insert staging row
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pricing.ebay_scraped_sold "
            "(item_id, title, source_product_id, price_cents, currency, marketplace_id, "
            " condition_id, finish_id, language_id, sold_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            "TEST-ITEM-001",
            "Sheoldred the Apocalypse DMU Foil NM MTG",
            source_product_id,
            1250,          # $12.50 USD
            "USD",
            "EBAY-US",
            1,             # condition_id=1 → NM
            2,             # finish_id=2 → FOIL
            language_id,
            _YESTERDAY,
        )

    # Step 2: run promote_sold_obs with real repos
    async with db_pool.acquire() as conn:
        result = await promote_sold_obs(
            ebay_sales_repository=EbaySalesRepository(conn),
            ebay_scrape_repository=EbayScrapeSoldRepository(conn),
            fx_rates_repository=FxRatesRepository(conn),
        )

    assert result["promoted"] == 1, (
        f"Expected 1 row promoted, got {result['promoted']}. "
        "Check that GET_UNPROMOTED_SCRAPED filters by promoted_to_obs=false and source_product_id IS NOT NULL."
    )

    # Step 3: verify price_observation
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sold_avg_cents, sold_count FROM pricing.price_observation "
            "WHERE source_product_id = $1",
            source_product_id,
        )

    assert row is not None, (
        f"No row found in price_observation for source_product_id={source_product_id}. "
        "Check that upsert_price_observation writes to pricing.price_observation."
    )
    assert row["sold_avg_cents"] == 1250, (
        f"Expected sold_avg_cents=1250, got {row['sold_avg_cents']}. "
        "Check _aggregate in promote_sold_obs_service.py."
    )
    assert row["sold_count"] == 1
