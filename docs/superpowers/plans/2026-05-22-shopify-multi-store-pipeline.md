# Shopify Multi-Store Price Ingestion Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a weekly Celery pipeline that fetches `/products.json` from every registered Shopify storefront, stages prices into `pricing.shopify_staging_raw`, and promotes them into `pricing.price_observation` so they appear in the existing frontend price chart alongside TCGPlayer/MTGStock data.

**Architecture:** Celery `chain` of 4 service steps registered with `@ServiceRegistry.register` and tracked with `track_step`, running every Sunday 06:00 AEST. Each store is a row in `markets.market_ref` linked to a `pricing.price_source` row. Prices land in `pricing.price_observation` — no new tables or API endpoints.

**Tech Stack:** FastAPI, Celery, asyncpg, aiohttp (for storefront fetch), pandas, pyarrow/fastparquet, PostgreSQL/TimescaleDB. Existing helpers: `process_json_dir_to_parquet`, `stage_data_from_parquet` (reused with compatible directory layout — see Task 5 notes).

**Spec:** `docs/superpowers/specs/2026-05-22-shopify-multi-store-pipeline-design.md`

**Work branch:** `feat/shopify-multi-store-pipeline`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `database/SQL/migrations/migration_45_shopify_market_pipeline.sql` | Schema changes + seed data |
| Modify | `database/SQL/schemas/07_shopify_staging.sql` | Fix broken `stage_to_price_observation()` (replace with no-op warning) |
| Create | `core/repositories/app_integration/shopify/pipeline_repository.py` | New repo: market listing, tcg_id lookup, source_product bootstrap, obs insert |
| Create | `core/services/app_integration/shopify/pipeline_service.py` | 4 registered pipeline steps |
| Modify | `core/repositories/app_integration/shopify/market_queries.py` | Add `markets.` schema prefix + `source_id` column |
| Modify | `core/framework/registry.py` | Register `shopify_pipeline` repository |
| Modify | `core/service_modules.py` | Add new pipeline_service module to `backend` + `celery` namespaces |
| Modify | `worker/tasks/pipelines.py` | Add `shopify_weekly_pipeline` task |
| Modify | `worker/celeryconfig.py` | Add Sunday 06:00 AEST beat schedule entry |
| Create | `tests/unit/core/test_shopify_pipeline.py` | Unit tests for variation mapping + price conversion |

All paths are relative to `src/automana/`.

---

## Task 1: Create the git branch

- [ ] **Step 1: Create and check out the feature branch**

```bash
git checkout -b feat/shopify-multi-store-pipeline
```

- [ ] **Step 2: Verify clean state**

```bash
git status
```
Expected: `nothing to commit, working tree clean`

---

## Task 2: Migration 45 — Schema changes + seed data

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_45_shopify_market_pipeline.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migration_45_shopify_market_pipeline.sql
BEGIN;

-- 1. Link each market store to a price_source row
ALTER TABLE markets.market_ref
    ADD COLUMN IF NOT EXISTS source_id SMALLINT
        REFERENCES pricing.price_source(source_id);

-- 2. Store Shopify product handle (for buy-link URL) and title on product_ref
ALTER TABLE markets.product_ref
    ADD COLUMN IF NOT EXISTS handle TEXT,
    ADD COLUMN IF NOT EXISTS title  TEXT;

-- 3. Add source_id to staging so promote step knows which store each row is from
ALTER TABLE pricing.shopify_staging_raw
    ADD COLUMN IF NOT EXISTS source_id SMALLINT
        REFERENCES pricing.price_source(source_id);

-- 4. Register Shopify stores as price sources (AU stores to start)
INSERT INTO pricing.price_source (code, name, currency_code) VALUES
    ('gg_brisbane', 'Good Games Brisbane', 'AUD'),
    ('gg_sydney',   'Good Games Sydney',   'AUD')
ON CONFLICT (code) DO NOTHING;

-- 5. Register 'shopify' as a data provider
INSERT INTO pricing.data_provider (code, description)
VALUES ('shopify', 'Shopify Storefront /products.json scrape')
ON CONFLICT (code) DO NOTHING;

-- 6. Wire existing market_ref rows to their source rows
--    Update Good Games Brisbane market (adjust name to match your actual market_ref.name)
UPDATE markets.market_ref mr
SET source_id = ps.source_id
FROM pricing.price_source ps
WHERE ps.code = 'gg_brisbane'
  AND lower(mr.name) LIKE '%brisbane%'
  AND mr.source_id IS NULL;

UPDATE markets.market_ref mr
SET source_id = ps.source_id
FROM pricing.price_source ps
WHERE ps.code = 'gg_sydney'
  AND lower(mr.name) LIKE '%sydney%'
  AND mr.source_id IS NULL;

COMMIT;
```

- [ ] **Step 2: Verify the file exists**

```bash
ls src/automana/database/SQL/migrations/migration_45_shopify_market_pipeline.sql
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_45_shopify_market_pipeline.sql
git commit -m "feat(shopify): migration_45 — add source_id FK to market_ref, handle/title to product_ref, source_id to staging"
```

---

## Task 3: Fix the broken schema file comment + update market queries

**Files:**
- Modify: `src/automana/database/SQL/schemas/07_shopify_staging.sql`
- Modify: `src/automana/core/repositories/app_integration/shopify/market_queries.py`

- [ ] **Step 1: Replace the broken `stage_to_price_observation` body with a clear notice**

Open `src/automana/database/SQL/schemas/07_shopify_staging.sql`. Find the `CREATE OR REPLACE PROCEDURE pricing.stage_to_price_observation()` block. Replace the entire procedure body (between `AS $$ BEGIN` and `END; $$`) with:

```sql
CREATE OR REPLACE PROCEDURE pricing.stage_to_price_observation()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE
        'pricing.stage_to_price_observation is intentionally a no-op. '
        'Shopify observations are promoted in Python by the '
        'shopify.pipeline.promote_observations service step.';
END;
$$;
```

- [ ] **Step 2: Update `market_queries.py` — add schema prefix and source_id**

Replace the entire content of `src/automana/core/repositories/app_integration/shopify/market_queries.py` with:

```python
insert_market_query = """
    INSERT INTO markets.market_ref (name, api_url, country_code, city)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (name, city, country_code) DO NOTHING;
"""

select_market_id_query = """
    SELECT market_id FROM markets.market_ref WHERE name = $1;
"""

select_all_markets_query = """
    SELECT market_id, name, api_url, country_code, city, source_id, created_at, updated_at
    FROM markets.market_ref;
"""

select_active_pipeline_markets_query = """
    SELECT mr.market_id, mr.name, mr.api_url, mr.country_code, mr.source_id
    FROM markets.market_ref mr
    WHERE mr.api_url IS NOT NULL
      AND mr.source_id IS NOT NULL;
"""
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/database/SQL/schemas/07_shopify_staging.sql \
        src/automana/core/repositories/app_integration/shopify/market_queries.py
git commit -m "fix(shopify): replace broken stage_to_price_observation with no-op notice; add schema prefix + source_id to market queries"
```

---

## Task 4: Create the Shopify pipeline repository

**Files:**
- Create: `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py`
- Test: `tests/unit/core/test_shopify_pipeline.py` (started here, extended in Task 6)

This repository handles all DB operations specific to the pipeline: listing active markets, resolving `tcg_id → card_version_id`, bootstrapping `product_ref / mtg_card_products / source_product`, and COPY-inserting observations. It does **not** replace the existing `MarketRepository` or `ProductRepository`.

- [ ] **Step 1: Write the failing test for `_map_variation`**

Create `tests/unit/core/test_shopify_pipeline.py`:

```python
import pytest
from automana.core.repositories.app_integration.shopify.pipeline_repository import (
    _map_variation,
)


@pytest.mark.parametrize("variation,expected_condition,expected_finish", [
    ("Near Mint",             "NM",  "nonfoil"),
    ("Near Mint Foil",        "NM",  "foil"),
    ("Lightly Played",        "LP",  "nonfoil"),
    ("Lightly Played Foil",   "LP",  "foil"),
    ("Moderately Played",     "MP",  "nonfoil"),
    ("Moderately Played Foil","MP",  "foil"),
    ("Heavily Played",        "HP",  "nonfoil"),
    ("Heavily Played Foil",   "HP",  "foil"),
    ("Damaged",               "DMG", "nonfoil"),
    ("Damaged Foil",          "DMG", "foil"),
])
def test_map_variation(variation, expected_condition, expected_finish):
    condition_code, finish_code = _map_variation(variation)
    assert condition_code == expected_condition
    assert finish_code == expected_finish


def test_map_variation_unknown_defaults_to_nm_nonfoil():
    condition_code, finish_code = _map_variation("Unknown Grade")
    assert condition_code == "NM"
    assert finish_code == "nonfoil"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/arthur/projects/AutoMana && .venv/bin/pytest tests/unit/core/test_shopify_pipeline.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — function does not exist yet.

- [ ] **Step 3: Create `pipeline_repository.py`**

Create `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py`:

```python
import io
import logging
from typing import Optional
import pandas as pd
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_VARIATION_CONDITION_MAP = {
    "near mint":         "NM",
    "lightly played":    "LP",
    "slightly played":   "LP",
    "moderately played": "MP",
    "heavily played":    "HP",
    "damaged":           "DMG",
}


def _map_variation(variation: str) -> tuple[str, str]:
    """Return (condition_code, finish_code) from a Shopify variant title."""
    lower = variation.lower().strip()
    is_foil = lower.endswith(" foil")
    base = lower[: -len(" foil")].strip() if is_foil else lower
    condition = _VARIATION_CONDITION_MAP.get(base, "NM")
    finish = "foil" if is_foil else "nonfoil"
    return condition, finish


class ShopifyPipelineRepository(AbstractRepository):
    @property
    def name(self) -> str:
        return "ShopifyPipelineRepository"

    async def get_active_pipeline_markets(self) -> list[dict]:
        """Returns markets that have api_url AND source_id set, including price_source code."""
        rows = await self.connection.fetch(
            """
            SELECT mr.market_id, mr.name, mr.api_url, mr.country_code,
                   mr.source_id, ps.code AS source_code
            FROM markets.market_ref mr
            JOIN pricing.price_source ps ON ps.source_id = mr.source_id
            WHERE mr.api_url IS NOT NULL AND mr.source_id IS NOT NULL
            """
        )
        return [dict(r) for r in rows]

    async def upsert_product_handles(self, rows: list[dict]) -> None:
        """Upsert handle + title on markets.product_ref.
        Each dict must have: product_id (str), market_id (int), handle (str), title (str).
        """
        if not rows:
            return
        await self.connection.executemany(
            """
            INSERT INTO markets.product_ref (product_shop_id, product_id, market_id, handle, title)
            VALUES ($1, $1, $2, $3, $4)
            ON CONFLICT (product_shop_id)
            DO UPDATE SET handle = EXCLUDED.handle,
                          title  = EXCLUDED.title,
                          updated_at = NOW()
            """,
            [(str(r["product_id"]), r["market_id"], r.get("handle"), r.get("title")) for r in rows],
        )

    async def find_card_versions_by_tcg_ids(self, tcg_ids: list[int]) -> dict[int, str]:
        """Map tcg_id → card_version_id (UUID as str). Unmapped IDs are omitted."""
        if not tcg_ids:
            return {}
        rows = await self.connection.fetch(
            """
            SELECT cei.value::BIGINT AS tcg_id, cei.card_version_id::TEXT
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
                ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
               AND cir.identifier_name = 'tcgplayer_id'
            WHERE cei.value::BIGINT = ANY($1::BIGINT[])
            """,
            tcg_ids,
        )
        return {r["tcg_id"]: r["card_version_id"] for r in rows}

    async def bootstrap_source_products(
        self, card_version_ids: list[str], source_id: int
    ) -> dict[str, int]:
        """Ensure product_ref + mtg_card_products + source_product rows exist for each
        card_version_id/source_id pair. Returns {card_version_id: source_product_id}."""
        if not card_version_ids:
            return {}

        # Create missing product_ref rows
        await self.connection.execute(
            """
            INSERT INTO pricing.product_ref (product_id, game_id)
            SELECT uuid_generate_v4(), cg.game_id
            FROM unnest($1::UUID[]) AS cv(card_version_id)
            JOIN pricing.card_game cg ON cg.code = 'mtg'
            WHERE NOT EXISTS (
                SELECT 1 FROM pricing.mtg_card_products mcp
                WHERE mcp.card_version_id = cv.card_version_id
            )
            """,
            card_version_ids,
        )

        # Create missing mtg_card_products rows
        await self.connection.execute(
            """
            INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
            SELECT pr.product_id, cv.card_version_id
            FROM unnest($1::UUID[]) AS cv(card_version_id)
            JOIN pricing.product_ref pr ON pr.product_id = (
                SELECT product_id FROM pricing.mtg_card_products
                WHERE card_version_id = cv.card_version_id
                LIMIT 1
            )
            ON CONFLICT (card_version_id) DO NOTHING
            """,
            card_version_ids,
        )

        # Create missing source_product rows
        await self.connection.execute(
            """
            INSERT INTO pricing.source_product (product_id, source_id)
            SELECT mcp.product_id, $2
            FROM unnest($1::UUID[]) AS cv(card_version_id)
            JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
            ON CONFLICT (product_id, source_id) DO NOTHING
            """,
            card_version_ids,
            source_id,
        )

        # Fetch source_product_id for each card_version_id
        rows = await self.connection.fetch(
            """
            SELECT mcp.card_version_id::TEXT, sp.source_product_id
            FROM unnest($1::UUID[]) AS cv(card_version_id)
            JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
            JOIN pricing.source_product sp
                ON sp.product_id = mcp.product_id AND sp.source_id = $2
            """,
            card_version_ids,
            source_id,
        )
        return {r["card_version_id"]: r["source_product_id"] for r in rows}

    async def bulk_copy_observations(self, df: pd.DataFrame) -> int:
        """COPY DataFrame into pricing.price_observation. Returns row count inserted."""
        if df.empty:
            return 0
        buf = io.BytesIO()
        df.to_csv(buf, index=False, header=True, encoding="utf-8")
        buf.seek(0)
        await self.connection.copy_to_table(
            "price_observation",
            source=buf,
            schema_name="pricing",
            format="csv",
            header=True,
        )
        return len(df)

    async def truncate_staging(self) -> None:
        await self.connection.execute("TRUNCATE pricing.shopify_staging_raw;")

    async def get_staging_rows(self) -> list[dict]:
        """Fetch all staged rows for promote step."""
        rows = await self.connection.fetch(
            """
            SELECT product_id, date, variation, price, scraped_at, tcg_id, source_id
            FROM pricing.shopify_staging_raw
            WHERE tcg_id IS NOT NULL AND source_id IS NOT NULL
            """
        )
        return [dict(r) for r in rows]

    async def get_reference_ids(self) -> dict:
        """Fetch static reference IDs needed to build price_observation rows."""
        sell_type = await self.connection.fetchrow(
            "SELECT transaction_type_id FROM pricing.transaction_type WHERE transaction_type_code = 'sell'"
        )
        dp = await self.connection.fetchrow(
            "SELECT data_provider_id FROM pricing.data_provider WHERE code = 'shopify'"
        )
        lang = await self.connection.fetchrow(
            "SELECT language_id FROM card_catalog.language_ref WHERE language_code = 'en'"
        )
        conditions = await self.connection.fetch(
            "SELECT code, condition_id FROM pricing.card_condition"
        )
        finishes = await self.connection.fetch(
            "SELECT code, finish_id FROM card_catalog.card_finished"
        )
        return {
            "sell_type_id": sell_type["transaction_type_id"],
            "data_provider_id": dp["data_provider_id"],
            "language_id": lang["language_id"],
            "conditions": {r["code"]: r["condition_id"] for r in conditions},
            "finishes": {r["code"].lower(): r["finish_id"] for r in finishes},
        }

    async def add(self): raise NotImplementedError
    async def delete(self, id): raise NotImplementedError
    async def get(self, id): raise NotImplementedError
    async def list(self): raise NotImplementedError
    async def update(self, item): raise NotImplementedError
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/arthur/projects/AutoMana && .venv/bin/pytest tests/unit/core/test_shopify_pipeline.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/pipeline_repository.py \
        tests/unit/core/test_shopify_pipeline.py
git commit -m "feat(shopify): ShopifyPipelineRepository + variation mapping tests"
```

---

## Task 5: Create the pipeline service (4 registered steps)

**Files:**
- Create: `src/automana/core/services/app_integration/shopify/pipeline_service.py`

The four steps are:
1. `shopify.pipeline.fetch_all_markets` — GET `/products.json` from each active market, save JSON files to disk
2. `shopify.pipeline.process_to_parquet` — convert saved JSON to per-product parquet (calls existing `process_json_dir_to_parquet`)
3. `shopify.pipeline.stage_raw` — COPY parquet data into `pricing.shopify_staging_raw` (calls existing `stage_data_from_parquet`)
4. `shopify.pipeline.promote_observations` — map staging → `pricing.price_observation`

- [ ] **Step 1: Write the failing test for price-to-cents conversion**

Add to `tests/unit/core/test_shopify_pipeline.py`:

```python
from automana.core.services.app_integration.shopify.pipeline_service import (
    _price_to_cents,
    _build_obs_dataframe,
)
from decimal import Decimal


def test_price_to_cents_rounds_correctly():
    assert _price_to_cents(Decimal("4.99")) == 499
    assert _price_to_cents(Decimal("10.00")) == 1000
    assert _price_to_cents(Decimal("0.50")) == 50
    assert _price_to_cents(None) is None


def test_build_obs_dataframe_excludes_unmapped_rows():
    refs = {
        "sell_type_id": 1,
        "data_provider_id": 5,
        "language_id": 1,
        "conditions": {"NM": 1, "LP": 2},
        "finishes": {"nonfoil": 1, "foil": 2},
    }
    staging_rows = [
        {"product_id": 100, "date": "2026-05-18", "variation": "Near Mint",
         "price": Decimal("4.99"), "scraped_at": "2026-05-18", "tcg_id": 999, "source_id": 3},
        {"product_id": 101, "date": "2026-05-18", "variation": "Near Mint Foil",
         "price": Decimal("9.99"), "scraped_at": "2026-05-18", "tcg_id": None, "source_id": 3},
    ]
    tcg_to_cv = {999: "aaaaaaaa-0000-0000-0000-000000000001"}
    cv_to_sp = {"aaaaaaaa-0000-0000-0000-000000000001": 42}

    df = _build_obs_dataframe(staging_rows, tcg_to_cv, cv_to_sp, refs)
    assert len(df) == 1  # row with tcg_id=None excluded
    assert df.iloc[0]["source_product_id"] == 42
    assert df.iloc[0]["list_avg_cents"] == 499
    assert df.iloc[0]["finish_id"] == 1  # nonfoil
    assert df.iloc[0]["condition_id"] == 1  # NM
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/arthur/projects/AutoMana && .venv/bin/pytest tests/unit/core/test_shopify_pipeline.py::test_price_to_cents_rounds_correctly tests/unit/core/test_shopify_pipeline.py::test_build_obs_dataframe_excludes_unmapped_rows -v 2>&1 | head -20
```

Expected: `ImportError` — module not yet created.

- [ ] **Step 3: Create `pipeline_service.py`**

Create `src/automana/core/services/app_integration/shopify/pipeline_service.py`:

```python
import asyncio
import glob
import json
import logging
import os
from decimal import Decimal
from typing import Optional

import aiohttp
import pandas as pd

from automana.core.repositories.app_integration.shopify.market_repository import MarketRepository
from automana.core.repositories.app_integration.shopify.pipeline_repository import (
    ShopifyPipelineRepository,
    _map_variation,
)
from automana.core.repositories.app_integration.shopify.product_repository import ProductRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.shopify.data_staging_service import (
    process_json_dir_to_parquet,
    stage_data_from_parquet,
)
from automana.core.services.ops.pipeline_services import track_step

logger = logging.getLogger(__name__)

_SHOPIFY_DATA_ROOT = os.getenv("SHOPIFY_DATA_ROOT", "/data/automana_data/shopify")


def _price_to_cents(price) -> Optional[int]:
    if price is None:
        return None
    return int(Decimal(str(price)) * 100)


def _build_obs_dataframe(
    staging_rows: list[dict],
    tcg_to_cv: dict[int, str],
    cv_to_sp: dict[str, int],
    refs: dict,
) -> pd.DataFrame:
    """Convert staging rows → DataFrame ready for COPY into price_observation."""
    rows = []
    for r in staging_rows:
        tcg_id = r.get("tcg_id")
        if tcg_id is None:
            continue
        card_version_id = tcg_to_cv.get(int(tcg_id))
        if card_version_id is None:
            continue
        source_product_id = cv_to_sp.get(card_version_id)
        if source_product_id is None:
            continue

        condition_code, finish_code = _map_variation(r["variation"] or "Near Mint")
        condition_id = refs["conditions"].get(condition_code)
        finish_id = refs["finishes"].get(finish_code)
        if condition_id is None or finish_id is None:
            continue

        rows.append(
            {
                "ts_date": str(r["date"])[:10],
                "price_type_id": refs["sell_type_id"],
                "finish_id": finish_id,
                "condition_id": condition_id,
                "language_id": refs["language_id"],
                "list_low_cents": None,
                "list_avg_cents": _price_to_cents(r["price"]),
                "sold_avg_cents": None,
                "list_count": None,
                "sold_count": None,
                "source_product_id": source_product_id,
                "data_provider_id": refs["data_provider_id"],
                "scraped_at": str(r["scraped_at"]),
            }
        )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=[
            "ts_date", "price_type_id", "finish_id", "condition_id", "language_id",
            "list_low_cents", "list_avg_cents", "sold_avg_cents", "list_count",
            "sold_count", "source_product_id", "data_provider_id", "scraped_at",
        ]
    )


async def _fetch_all_pages(api_url: str, source_id: int, data_root: str) -> tuple[str, int]:
    """Paginate /products.json?limit=250 and save pages as page_N_products.json.

    Saves to {data_root}/{source_id}_fetch/page_N_products.json — this layout is
    compatible with process_json_dir_to_parquet which globs for
    {data_root}/{source_id}_*/**/*products.json.

    Returns (out_dir, page_count).
    """
    out_dir = os.path.join(data_root, f"{source_id}_fetch")
    os.makedirs(out_dir, exist_ok=True)
    page = 0
    next_url = f"{api_url.rstrip('/')}/products.json?limit=250"
    async with aiohttp.ClientSession() as session:
        while next_url:
            async with session.get(next_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()
                products = data.get("products") or data.get("items") or []
                if not products:
                    break
                page_path = os.path.join(out_dir, f"page_{page}_products.json")
                with open(page_path, "w", encoding="utf-8") as f:
                    json.dump({"items": products}, f)
                page += 1
                link_header = resp.headers.get("Link", "")
                next_url = None
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split(";")[0].strip().strip("<>")
                        break
    return out_dir, page


@ServiceRegistry.register(
    path="shopify.pipeline.fetch_all_markets",
    db_repositories=["shopify_pipeline", "ops"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def fetch_all_markets(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
):
    markets = await shopify_pipeline_repository.get_active_pipeline_markets()
    logger.info("fetch_all_markets: found active markets", extra={"count": len(markets)})
    market_dirs = {}
    for market in markets:
        market_id = market["market_id"]
        source_id = market["source_id"]
        api_url = market["api_url"]
        async with track_step(ops_repository, ingestion_run_id, f"fetch_storefront_{market_id}"):
            out_dir, pages = await _fetch_all_pages(api_url, source_id, _SHOPIFY_DATA_ROOT)
            logger.info(
                "fetch_all_markets: fetched pages",
                extra={"market_id": market_id, "source_id": source_id, "pages": pages},
            )
            market_dirs[market_id] = out_dir
    return {"market_dirs": market_dirs, "markets": markets}


@ServiceRegistry.register(
    path="shopify.pipeline.process_to_parquet",
    db_repositories=["market", "shopify_pipeline", "ops"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def process_to_parquet(
    market_repository: MarketRepository,
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    market_dirs: dict = None,
    markets: list = None,
):
    parquet_dirs = {}
    for market in (markets or []):
        market_id = market["market_id"]
        # IMPORTANT: process_json_dir_to_parquet uses market_code to query
        # pricing.price_source.code, NOT markets.market_ref.name.
        # Pass the price_source code (e.g. 'gg_brisbane') as market_code.
        source_code = market.get("source_code")  # populated by fetch step context
        parquet_dir = os.path.join(_SHOPIFY_DATA_ROOT, "parquet", str(market_id))

        async with track_step(ops_repository, ingestion_run_id, f"process_to_parquet_{market_id}"):
            await process_json_dir_to_parquet(
                market_repository=market_repository,
                path_to_json=_SHOPIFY_DATA_ROOT,  # process_json_dir_to_parquet globs within this
                market_code=source_code,            # price_source.code, e.g. 'gg_brisbane'
                output_path=parquet_dir,
            )
            # Upsert handle + title from info.json files.
            # Use market["market_id"] (markets.market_ref PK) — NOT info["shop_id"]
            # which is price_source.source_id (a different integer).
            info_files = glob.glob(os.path.join(parquet_dir, "*", "info.json"))
            handle_rows = []
            for info_path in info_files:
                with open(info_path) as f:
                    info = json.load(f)
                handle_rows.append(
                    {
                        "product_id": str(info["product_id"]),
                        "market_id": market_id,       # markets.market_ref.market_id
                        "handle": info.get("handle"),
                        "title": info.get("title"),
                    }
                )
            if handle_rows:
                await shopify_pipeline_repository.upsert_product_handles(handle_rows)

            parquet_dirs[market_id] = parquet_dir
    return {"parquet_dirs": parquet_dirs, "markets": markets}


@ServiceRegistry.register(
    path="shopify.pipeline.stage_raw",
    db_repositories=["product", "shopify_pipeline", "ops"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def stage_raw(
    product_repository: ProductRepository,
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    parquet_dirs: dict = None,
    markets: list = None,
):
    for market in (markets or []):
        market_id = market["market_id"]
        source_id = market["source_id"]
        parquet_dir = (parquet_dirs or {}).get(market_id, os.path.join(_SHOPIFY_DATA_ROOT, "parquet", str(market_id)))

        async with track_step(ops_repository, ingestion_run_id, f"stage_raw_{market_id}"):
            await stage_data_from_parquet(
                product_repository=product_repository,
                parquet_base_path=parquet_dir,
            )
            # Stamp source_id on the rows we just staged (product_id links to this market)
            await shopify_pipeline_repository.connection.execute(
                """
                UPDATE pricing.shopify_staging_raw ssr
                SET source_id = $1
                FROM markets.product_ref mpr
                WHERE mpr.product_id = ssr.product_id::TEXT
                  AND mpr.market_id = $2
                  AND ssr.source_id IS NULL
                """,
                source_id,
                market_id,
            )
    return {"markets": markets}


@ServiceRegistry.register(
    path="shopify.pipeline.promote_observations",
    db_repositories=["shopify_pipeline", "ops"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def promote_observations(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    markets: list = None,
):
    async with track_step(ops_repository, ingestion_run_id, "promote_observations"):
        staging_rows = await shopify_pipeline_repository.get_staging_rows()
        if not staging_rows:
            logger.info("promote_observations: no staged rows found")
            return {}

        refs = await shopify_pipeline_repository.get_reference_ids()

        tcg_ids = list({int(r["tcg_id"]) for r in staging_rows if r.get("tcg_id")})
        tcg_to_cv = await shopify_pipeline_repository.find_card_versions_by_tcg_ids(tcg_ids)

        # Bootstrap source_products per source_id group
        cv_to_sp: dict[str, int] = {}
        source_ids = list({r["source_id"] for r in staging_rows if r.get("source_id")})
        for source_id in source_ids:
            relevant_tcg_ids = [
                int(r["tcg_id"]) for r in staging_rows
                if r.get("tcg_id") and r.get("source_id") == source_id
            ]
            cv_ids = list({tcg_to_cv[t] for t in relevant_tcg_ids if t in tcg_to_cv})
            mapping = await shopify_pipeline_repository.bootstrap_source_products(cv_ids, source_id)
            cv_to_sp.update(mapping)

        df = _build_obs_dataframe(staging_rows, tcg_to_cv, cv_to_sp, refs)
        inserted = await shopify_pipeline_repository.bulk_copy_observations(df)
        await shopify_pipeline_repository.truncate_staging()

        logger.info(
            "promote_observations: complete",
            extra={"staged_rows": len(staging_rows), "inserted": inserted},
        )
        return {"inserted": inserted}
```

- [ ] **Step 4: Run the unit tests to verify they pass**

```bash
cd /home/arthur/projects/AutoMana && .venv/bin/pytest tests/unit/core/test_shopify_pipeline.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/shopify/pipeline_service.py \
        tests/unit/core/test_shopify_pipeline.py
git commit -m "feat(shopify): pipeline_service — 4 registered steps: fetch, process, stage, promote"
```

---

## Task 6: Register the new repository and service module

**Files:**
- Modify: `src/automana/core/framework/registry.py`
- Modify: `src/automana/core/service_modules.py`

- [ ] **Step 1: Register `ShopifyPipelineRepository` in `framework/wiring.py`**

In `src/automana/core/framework/registry.py`, find the block with `# Shop Meta repositories` and add after the existing three Shopify registrations:

```python
ServiceRegistry.register_db_repository(
    "shopify_pipeline",
    "automana.core.repositories.app_integration.shopify.pipeline_repository",
    "ShopifyPipelineRepository",
)
```

- [ ] **Step 2: Add `pipeline_service` to both namespaces in `service_modules.py`**

In `src/automana/core/service_modules.py`, add the following line to the `"backend"` list (after the existing shopify/mtg_stock entries):

```python
"automana.core.services.app_integration.shopify.pipeline_service",
```

Add the same line to the `"celery"` list (after the MTGStock entries).

Add it also to the `"all"` list if one exists.

- [ ] **Step 3: Verify imports are clean**

```bash
cd /home/arthur/projects/AutoMana && .venv/bin/python -c "
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.shopify.pipeline_service import fetch_all_markets
print('Import OK')
"
```

Expected: `Import OK`

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/framework/registry.py src/automana/core/service_modules.py
git commit -m "feat(shopify): register ShopifyPipelineRepository + add pipeline_service to service modules"
```

---

## Task 7: Add the Celery task and beat schedule

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 1: Add `shopify_weekly_pipeline` to `pipelines.py`**

Open `src/automana/worker/tasks/pipelines.py`. After the last `@shared_task` definition, add:

```python
@shared_task(name="automana.worker.tasks.pipelines.shopify_weekly_pipeline", bind=True)
def shopify_weekly_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"shopify_weekly:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting Shopify weekly pipeline", extra={"run_key": run_key})
    wf = chain(
        run_service.s(
            "ops.pipeline_services.start_run",
            pipeline_name="shopify_weekly",
            source_name="shopify",
            run_key=run_key,
            celery_task_id=self.request.id,
        ),
        run_service.s("shopify.pipeline.fetch_all_markets"),
        run_service.s("shopify.pipeline.process_to_parquet"),
        run_service.s("shopify.pipeline.stage_raw"),
        run_service.s("shopify.pipeline.promote_observations"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id
```

- [ ] **Step 2: Add the beat schedule entry to `celeryconfig.py`**

In `src/automana/worker/celeryconfig.py`, add to the `beat_schedule` dict (after `"pricing-archive-to-weekly"`):

```python
    "shopify-ingest-weekly": {
        "task": "automana.worker.tasks.pipelines.shopify_weekly_pipeline",
        "schedule": crontab(day_of_week=0, hour=6, minute=0),  # Sunday 06:00 AEST
    },
```

- [ ] **Step 3: Verify the task imports cleanly**

```bash
cd /home/arthur/projects/AutoMana && .venv/bin/python -c "
from automana.worker.tasks.pipelines import shopify_weekly_pipeline
print('Task registered:', shopify_weekly_pipeline.name)
"
```

Expected: `Task registered: automana.worker.tasks.pipelines.shopify_weekly_pipeline`

- [ ] **Step 4: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py src/automana/worker/celeryconfig.py
git commit -m "feat(shopify): add shopify_weekly_pipeline Celery task + Sunday 06:00 AEST beat schedule"
```

---

## Task 8: Additional unit tests for edge cases

**Files:**
- Modify: `tests/unit/core/test_shopify_pipeline.py`

- [ ] **Step 1: Add edge-case tests**

Append to `tests/unit/core/test_shopify_pipeline.py`:

```python
def test_build_obs_dataframe_empty_staging():
    refs = {
        "sell_type_id": 1, "data_provider_id": 5, "language_id": 1,
        "conditions": {"NM": 1}, "finishes": {"nonfoil": 1, "foil": 2},
    }
    df = _build_obs_dataframe([], {}, {}, refs)
    assert df.empty


def test_build_obs_dataframe_all_columns_present():
    from decimal import Decimal
    refs = {
        "sell_type_id": 1, "data_provider_id": 5, "language_id": 1,
        "conditions": {"NM": 1}, "finishes": {"nonfoil": 1, "foil": 2},
    }
    staging_rows = [
        {"product_id": 100, "date": "2026-05-18", "variation": "Near Mint",
         "price": Decimal("5.00"), "scraped_at": "2026-05-18", "tcg_id": 1, "source_id": 3},
    ]
    df = _build_obs_dataframe(staging_rows, {1: "uuid-1"}, {"uuid-1": 99}, refs)
    expected_cols = {
        "ts_date", "price_type_id", "finish_id", "condition_id", "language_id",
        "list_low_cents", "list_avg_cents", "sold_avg_cents", "list_count",
        "sold_count", "source_product_id", "data_provider_id", "scraped_at",
    }
    assert set(df.columns) == expected_cols
    assert df.iloc[0]["list_avg_cents"] == 500


def test_map_variation_case_insensitive():
    condition, finish = _map_variation("NEAR MINT FOIL")
    assert condition == "NM"
    assert finish == "foil"
```

- [ ] **Step 2: Run the full unit test file**

```bash
cd /home/arthur/projects/AutoMana && .venv/bin/pytest tests/unit/core/test_shopify_pipeline.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/core/test_shopify_pipeline.py
git commit -m "test(shopify): add edge-case unit tests for pipeline helpers"
```

---

## Self-Review Checklist (run before opening PR)

- [ ] `migration_45` applies cleanly: `psql -U automana_admin automana -f migration_45_shopify_market_pipeline.sql`
- [ ] All 4 service paths are importable: `python -c "from automana.core.services.app_integration.shopify.pipeline_service import *"`
- [ ] `ShopifyPipelineRepository` is in `framework/wiring.py`
- [ ] `pipeline_service` appears in both `backend` and `celery` namespaces in `service_modules.py`
- [ ] Beat schedule entry is present in `celeryconfig.py`
- [ ] All unit tests pass: `pytest tests/unit/core/test_shopify_pipeline.py -v`
- [ ] `aiohttp` is in `worker/requirements.txt` (add if missing: `aiohttp>=3.9`)
