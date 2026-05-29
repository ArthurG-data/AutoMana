# Sealed Product Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend AutoMana's pricing infrastructure to ingest and serve sealed MTG product prices from MTGJson's bulk data files.

**Architecture:** A new `pricing.sealed_products` subtype table extends the existing `product_ref` supertype. Prices land in the already-product-agnostic `pricing.price_observation` (T1) via a new staging table and promotion procedure. A `sealed_price_latest` snapshot provides O(1) current-price queries. The card pricing pipeline is untouched. Two read-only API endpoints expose sealed prices by set code.

**Tech Stack:** PostgreSQL + TimescaleDB, asyncpg, FastAPI, Celery, Python 3.12, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-05-26-sealed-product-pricing-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| CREATE | `src/automana/database/SQL/migrations/migration_51_sealed_product_pricing.sql` | Creates sealed tables + promotion procedure |
| CREATE | `src/automana/database/SQL/schemas/12_sealed_pricing.sql` | Canonical schema state for fresh builds |
| CREATE | `src/automana/core/repositories/pricing/sealed_pricing_repository.py` | All sealed DB queries/commands |
| CREATE | `src/automana/core/services/pricing/sealed_pricing_service.py` | Pipeline service steps (catalog bootstrap + promote) |
| MODIFY | `src/automana/core/services/app_integration/mtgjson/data_loader.py` | Route sealed UUIDs in `stream_to_staging` |
| CREATE | `src/automana/api/routers/mtg/sealed_pricing.py` | Two read endpoints |
| MODIFY | `src/automana/api/routers/mtg/__init__.py` | Mount sealed_pricing_router |
| MODIFY | `src/automana/worker/tasks/pipelines.py` | Add `daily_mtgjson_sealed_pipeline` task |
| CREATE | `tests/integration/services/sealed_pricing/conftest.py` | Shared fixtures |
| CREATE | `tests/integration/services/sealed_pricing/__init__.py` | Package marker |
| CREATE | `tests/integration/services/sealed_pricing/test_sealed_promotion.py` | End-to-end staging→T1→snapshot |
| CREATE | `tests/integration/api/test_sealed_pricing_router.py` | API endpoint tests |

---

## Task 1: Migration + Schema DDL

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_51_sealed_product_pricing.sql`
- Create: `src/automana/database/SQL/schemas/12_sealed_pricing.sql`

- [ ] **Step 1: Write `migration_51_sealed_product_pricing.sql`**

```sql
-- migration_51: Sealed product pricing tables, promotion procedure, and grants.
--
-- Creates three new tables:
--   pricing.sealed_products        — subtype of product_ref for sealed MTG products
--   pricing.sealed_price_latest    — current-price snapshot keyed on product_id
--   pricing.mtgjson_sealed_prices_staging — raw MTGJson sealed prices landing table
--
-- Also creates:
--   pricing.load_price_observation_from_mtgjson_sealed_staging() — promotion procedure
--
-- Card pricing pipeline (mtg_card_products, price_observation, etc.) is untouched.

-- ── sealed_products ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing.sealed_products (
    product_id      UUID        NOT NULL PRIMARY KEY
                                REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    set_id          UUID        REFERENCES card_catalog.sets(set_id),
    name            TEXT        NOT NULL,
    product_type    TEXT        NOT NULL,
    mtgjson_uuid    TEXT        NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sealed_products_set_id
    ON pricing.sealed_products (set_id);
CREATE INDEX IF NOT EXISTS idx_sealed_products_mtgjson_uuid
    ON pricing.sealed_products (mtgjson_uuid);

-- ── sealed_price_latest ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing.sealed_price_latest (
    product_id          UUID        NOT NULL
                                    REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    source_id           SMALLINT    NOT NULL
                                    REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
                                    REFERENCES pricing.transaction_type(transaction_type_id),
    price_date          DATE        NOT NULL,
    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sealed_price_latest_pk PRIMARY KEY (product_id, source_id, transaction_type_id),
    CONSTRAINT chk_spl_nonneg CHECK (
        (list_low_cents  IS NULL OR list_low_cents  >= 0) AND
        (list_avg_cents  IS NULL OR list_avg_cents  >= 0) AND
        (sold_avg_cents  IS NULL OR sold_avg_cents  >= 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_spl_product_source
    ON pricing.sealed_price_latest (product_id, source_id);

-- ── mtgjson_sealed_prices_staging ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing.mtgjson_sealed_prices_staging (
    id              SERIAL      PRIMARY KEY,
    sealed_uuid     TEXT        NOT NULL,
    price_source    TEXT        NOT NULL,
    price_type      TEXT,
    currency        TEXT        NOT NULL,
    price_value     FLOAT       NOT NULL,
    price_date      DATE        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_msps_sealed_uuid
    ON pricing.mtgjson_sealed_prices_staging (sealed_uuid);
CREATE INDEX IF NOT EXISTS idx_msps_price_date
    ON pricing.mtgjson_sealed_prices_staging (price_date);

GRANT TRUNCATE ON pricing.mtgjson_sealed_prices_staging TO app_rw, app_admin;

-- ── Promotion procedure ───────────────────────────────────────────────────────
CREATE OR REPLACE PROCEDURE pricing.load_price_observation_from_mtgjson_sealed_staging(
    batch_days INT DEFAULT 30
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_data_provider_id BIGINT;
    v_min DATE;
    v_max DATE;
    v_start DATE;
    v_end   DATE;
    v_upserted BIGINT := 0;
    v_deleted  BIGINT := 0;
    v_total_upserted BIGINT := 0;
    v_total_deleted  BIGINT := 0;
    v_is_ok BOOLEAN := FALSE;
BEGIN
    IF batch_days IS NULL OR batch_days <= 0 THEN
        RAISE EXCEPTION 'batch_days must be > 0 (got %)', batch_days;
    END IF;

    -- Normalize price_type
    UPDATE pricing.mtgjson_sealed_prices_staging
    SET price_type = CASE
        WHEN lower(price_type) IN ('retail', 'market') THEN 'sell'
        WHEN lower(price_type) IN ('buylist', 'directlow') THEN 'buy'
        ELSE lower(price_type)
    END;

    -- Normalize source names
    UPDATE pricing.mtgjson_sealed_prices_staging
    SET price_source = 'tcg'
    WHERE lower(price_source) = 'tcgplayer';

    COMMIT;

    SELECT dp.data_provider_id INTO v_data_provider_id
    FROM pricing.data_provider dp WHERE dp.code = 'mtgjson' LIMIT 1;

    IF v_data_provider_id IS NULL THEN
        RAISE EXCEPTION 'Missing pricing.data_provider row with code=mtgjson';
    END IF;

    SELECT min(price_date)::date, max(price_date)::date
    INTO v_min, v_max
    FROM pricing.mtgjson_sealed_prices_staging
    WHERE price_date IS NOT NULL;

    IF v_min IS NULL THEN
        RAISE NOTICE 'No rows in pricing.mtgjson_sealed_prices_staging to process.';
        RETURN;
    END IF;

    v_start := v_min;

    WHILE v_start <= v_max LOOP
        v_end := v_start + (batch_days - 1);

        BEGIN
            v_is_ok := FALSE;

            -- Upsert price_source rows for any new source codes in this batch
            INSERT INTO pricing.price_source (code, name, currency_code)
            SELECT DISTINCT s.price_source, s.price_source, s.currency
            FROM pricing.mtgjson_sealed_prices_staging s
            WHERE s.price_date BETWEEN v_start AND v_end
              AND s.price_source IS NOT NULL
              AND s.currency IS NOT NULL
            ON CONFLICT (code) DO NOTHING;

            WITH
            src AS (
                SELECT ps.source_id, ps.code, ps.currency_code
                FROM pricing.price_source ps
            ),
            prod AS (
                SELECT sp2.product_id, sp2.mtgjson_uuid
                FROM pricing.sealed_products sp2
            ),
            pairs AS (
                SELECT DISTINCT p.product_id, s.source_id
                FROM pricing.mtgjson_sealed_prices_staging st
                JOIN src s ON s.code = st.price_source
                JOIN prod p ON p.mtgjson_uuid = st.sealed_uuid
                WHERE st.price_date BETWEEN v_start AND v_end
                  AND st.sealed_uuid IS NOT NULL
            ),
            insert_source_product AS (
                INSERT INTO pricing.source_product (product_id, source_id)
                SELECT product_id, source_id FROM pairs
                ON CONFLICT (product_id, source_id) DO UPDATE
                    SET product_id = EXCLUDED.product_id
                RETURNING source_product_id, product_id, source_id
            ),
            staged AS (
                SELECT
                    s.id,
                    s.price_date AS ts_date,
                    s.price_source,
                    tt.transaction_type_id AS price_type_id,
                    s.currency,
                    s.sealed_uuid,
                    LEAST(round((s.price_value::NUMERIC) * 100), 2147483647::NUMERIC)::INT AS price_cents
                FROM pricing.mtgjson_sealed_prices_staging s
                JOIN pricing.transaction_type tt ON tt.transaction_type_code = s.price_type
                WHERE s.price_date BETWEEN v_start AND v_end
                  AND s.price_date IS NOT NULL
                  AND s.sealed_uuid IS NOT NULL
                  AND s.price_source IS NOT NULL
                  AND s.currency IS NOT NULL
                  AND s.price_value IS NOT NULL
            ),
            resolved AS (
                SELECT
                    st.id,
                    st.ts_date,
                    pricing.default_finish_id()    AS finish_id,
                    pricing.default_condition_id() AS condition_id,
                    card_catalog.default_language_id() AS language_id,
                    st.price_cents,
                    st.price_type_id,
                    isp.source_id,
                    isp.source_product_id,
                    prod.product_id
                FROM staged st
                JOIN src ON src.code = st.price_source
                JOIN prod ON prod.mtgjson_uuid = st.sealed_uuid
                JOIN insert_source_product isp
                    ON isp.product_id = prod.product_id
                   AND isp.source_id = src.source_id
            ),
            upserted AS (
                INSERT INTO pricing.price_observation (
                    ts_date, price_type_id, finish_id, condition_id, language_id,
                    list_low_cents, list_avg_cents, sold_avg_cents,
                    list_count, sold_count,
                    source_product_id, data_provider_id,
                    scraped_at, created_at, updated_at
                )
                SELECT DISTINCT ON (r.ts_date, r.source_product_id, r.price_type_id,
                                    r.finish_id, r.condition_id, r.language_id)
                    r.ts_date,
                    r.price_type_id,
                    r.finish_id,
                    r.condition_id,
                    r.language_id,
                    NULL::INT,
                    CASE WHEN r.price_type_id = 1 THEN r.price_cents END::INT,
                    CASE WHEN r.price_type_id = 2 THEN r.price_cents END::INT,
                    CASE WHEN r.price_type_id = 1 THEN 1 END::INT,
                    CASE WHEN r.price_type_id = 2 THEN 1 END::INT,
                    r.source_product_id,
                    v_data_provider_id,
                    now(), now(), now()
                FROM resolved r
                ORDER BY r.ts_date, r.source_product_id, r.price_type_id,
                         r.finish_id, r.condition_id, r.language_id
                ON CONFLICT (ts_date, source_product_id, price_type_id,
                             finish_id, condition_id, language_id, data_provider_id)
                DO UPDATE SET
                    list_avg_cents = EXCLUDED.list_avg_cents,
                    sold_avg_cents = EXCLUDED.sold_avg_cents,
                    list_count     = EXCLUDED.list_count,
                    sold_count     = EXCLUDED.sold_count,
                    scraped_at     = EXCLUDED.scraped_at,
                    updated_at     = now()
                RETURNING 1
            )
            SELECT count(*) INTO v_upserted FROM upserted;

            -- Upsert snapshot (advance only when newer)
            INSERT INTO pricing.sealed_price_latest (
                product_id, source_id, transaction_type_id,
                price_date, list_avg_cents, sold_avg_cents, n_providers, updated_at
            )
            SELECT DISTINCT ON (r.product_id, r.source_id, r.price_type_id)
                r.product_id,
                r.source_id,
                r.price_type_id,
                r.ts_date,
                CASE WHEN r.price_type_id = 1 THEN r.price_cents END::INT,
                CASE WHEN r.price_type_id = 2 THEN r.price_cents END::INT,
                1::SMALLINT,
                now()
            FROM resolved r
            ORDER BY r.product_id, r.source_id, r.price_type_id, r.ts_date DESC
            ON CONFLICT (product_id, source_id, transaction_type_id)
            DO UPDATE SET
                price_date     = EXCLUDED.price_date,
                list_avg_cents = EXCLUDED.list_avg_cents,
                sold_avg_cents = EXCLUDED.sold_avg_cents,
                n_providers    = EXCLUDED.n_providers,
                updated_at     = now()
            WHERE EXCLUDED.price_date >= pricing.sealed_price_latest.price_date;

            -- Delete resolved rows from staging
            WITH
            src AS (SELECT ps.source_id, ps.code FROM pricing.price_source ps),
            prod AS (SELECT sp2.product_id, sp2.mtgjson_uuid FROM pricing.sealed_products sp2),
            staged_ids AS (
                SELECT s.id
                FROM pricing.mtgjson_sealed_prices_staging s
                JOIN pricing.transaction_type tt ON tt.transaction_type_code = s.price_type
                JOIN src ON src.code = s.price_source
                JOIN prod ON prod.mtgjson_uuid = s.sealed_uuid
                JOIN pricing.source_product sp3
                    ON sp3.product_id = prod.product_id AND sp3.source_id = src.source_id
                WHERE s.price_date BETWEEN v_start AND v_end
                  AND s.price_date IS NOT NULL
                  AND s.sealed_uuid IS NOT NULL
                  AND s.price_source IS NOT NULL
                  AND s.currency IS NOT NULL
                  AND s.price_value IS NOT NULL
            )
            DELETE FROM pricing.mtgjson_sealed_prices_staging s
            USING staged_ids r WHERE s.id = r.id;

            GET DIAGNOSTICS v_deleted = ROW_COUNT;
            v_total_upserted := v_total_upserted + COALESCE(v_upserted, 0);
            v_total_deleted  := v_total_deleted  + COALESCE(v_deleted,  0);
            v_is_ok := TRUE;

        EXCEPTION WHEN OTHERS THEN
            v_is_ok := FALSE;
            RAISE WARNING 'Sealed batch % to % failed: %', v_start, v_end, SQLERRM;
        END;

        IF v_is_ok THEN
            RAISE NOTICE 'Sealed batch % to %: upserted %, deleted %',
                v_start, v_end, v_upserted, v_deleted;
            COMMIT;
        END IF;

        v_start := v_end + 1;
    END LOOP;

    RAISE NOTICE 'Done. Total upserted %, total deleted %', v_total_upserted, v_total_deleted;
END;
$$;

-- ── Grants ────────────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_products         TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_products                                  TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_price_latest      TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_price_latest                              TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.mtgjson_sealed_prices_staging TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.mtgjson_sealed_prices_staging                   TO app_ro;
GRANT EXECUTE ON PROCEDURE pricing.load_price_observation_from_mtgjson_sealed_staging(INT)
    TO app_celery, app_rw, app_admin;
```

- [ ] **Step 2: Write `12_sealed_pricing.sql` (identical DDL wrapped in BEGIN/COMMIT)**

```sql
BEGIN;
-- Canonical schema state for sealed product pricing.
-- Content is identical to migration_51_sealed_product_pricing.sql.
-- Applied on fresh container builds by the integration test runner.
-- See migration_51 for design rationale.

-- [paste the full DDL from Step 1 here — same content, minus the migration comment header]

COMMIT;
```

Copy the full DDL block from Step 1 into the `BEGIN; … COMMIT;` wrapper.

- [ ] **Step 3: Verify the migration applies cleanly against the dev DB**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
    < src/automana/database/SQL/migrations/migration_51_sealed_product_pricing.sql
```

Expected output: `CREATE TABLE`, `CREATE INDEX`, `GRANT`, `CREATE PROCEDURE` — no errors.

- [ ] **Step 4: Verify tables exist**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
    "\dt pricing.sealed*"
```

Expected:
```
                   List of relations
 Schema  |               Name               | Type  |  Owner
---------+----------------------------------+-------+----------
 pricing | sealed_price_latest              | table | ...
 pricing | sealed_products                  | table | ...
 pricing | mtgjson_sealed_prices_staging    | table | ...
```

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_51_sealed_product_pricing.sql \
        src/automana/database/SQL/schemas/12_sealed_pricing.sql
git commit -m "feat(db): add sealed product pricing tables and promotion procedure (migration_51)"
```

---

## Task 2: SealedPricingDBRepository

**Files:**
- Create: `src/automana/core/repositories/pricing/sealed_pricing_repository.py`
- Test: `tests/integration/services/sealed_pricing/test_sealed_promotion.py`
- Create: `tests/integration/services/sealed_pricing/__init__.py`
- Create: `tests/integration/services/sealed_pricing/conftest.py`

- [ ] **Step 1: Write the integration test (failing first)**

Create `tests/integration/services/sealed_pricing/__init__.py` (empty).

Create `tests/integration/services/sealed_pricing/conftest.py`:

```python
"""Shared fixtures for sealed pricing integration tests."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration]

_PRICE_DATE = date(2026, 3, 1)


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
```

Create `tests/integration/services/sealed_pricing/test_sealed_promotion.py`:

```python
"""Integration test: sealed staging promotion procedure and repository queries."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


async def test_sealed_products_table_exists(db_pool):
    """migration_51: sealed_products table must exist."""
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'pricing' AND table_name = 'sealed_products')"
        )
    assert exists, "pricing.sealed_products table not found — check migration_51"


async def test_sealed_price_latest_table_exists(db_pool):
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'pricing' AND table_name = 'sealed_price_latest')"
        )
    assert exists, "pricing.sealed_price_latest table not found"


async def test_staged_sealed_row_promotes_to_price_observation(db_pool, sealed_db):
    """One staged sealed row (tcgplayer/retail/USD) must land in price_observation after CALL."""
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
    assert count == 1, f"Expected 1 row in price_observation, got {count}"


async def test_snapshot_updated_after_promotion(db_pool, sealed_db):
    """After promotion, sealed_price_latest must contain one row for the product."""
    sealed_uuid = sealed_db["sealed_uuid"]
    product_id = sealed_db["product_id"]

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pricing.mtgjson_sealed_prices_staging "
            "(sealed_uuid, price_source, price_type, currency, price_value, price_date) "
            "VALUES ($1, 'tcgplayer', 'retail', 'USD', 89.99, '2026-03-02')",
            sealed_uuid,
        )
        await conn.execute(
            "CALL pricing.load_price_observation_from_mtgjson_sealed_staging()"
        )
        row = await conn.fetchrow(
            "SELECT list_avg_cents, price_date FROM pricing.sealed_price_latest "
            "WHERE product_id = $1",
            product_id,
        )

    assert row is not None, "No snapshot row found in sealed_price_latest"
    assert row["list_avg_cents"] == 8999, (
        f"Expected 8999 cents (=$89.99), got {row['list_avg_cents']}"
    )
```

- [ ] **Step 2: Run tests to confirm they fail (tables don't exist yet in test container)**

```bash
pytest tests/integration/services/sealed_pricing/ -v -m integration 2>&1 | head -30
```

Expected: FAIL — `pricing.sealed_products does not exist`.

- [ ] **Step 3: Write `sealed_pricing_repository.py`**

```python
"""DB repository for sealed product pricing queries and commands."""
from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_GET_SEALED_PRODUCTS_BY_SET = """
SELECT
    sp.product_id,
    sp.name,
    sp.product_type,
    sp.mtgjson_uuid,
    s.set_code
FROM pricing.sealed_products sp
JOIN card_catalog.sets s ON s.set_id = sp.set_id
WHERE lower(s.set_code) = lower($1)
ORDER BY sp.product_type, sp.name
"""

_GET_SEALED_PRICES_BY_SET = """
SELECT
    sp.product_id,
    sp.name,
    sp.product_type,
    sp.mtgjson_uuid,
    ps.code AS source,
    tt.transaction_type_code AS transaction_type,
    spl.price_date,
    spl.list_low_cents,
    spl.list_avg_cents,
    spl.sold_avg_cents
FROM pricing.sealed_price_latest spl
JOIN pricing.sealed_products sp ON sp.product_id = spl.product_id
JOIN pricing.price_source ps ON ps.source_id = spl.source_id
JOIN pricing.transaction_type tt ON tt.transaction_type_id = spl.transaction_type_id
JOIN card_catalog.sets s ON s.set_id = sp.set_id
WHERE lower(s.set_code) = lower($1)
ORDER BY sp.product_type, sp.name, ps.code
"""

_GET_SEALED_PRICE_LATEST = """
SELECT
    ps.code AS source,
    tt.transaction_type_code AS transaction_type,
    spl.price_date,
    spl.list_low_cents,
    spl.list_avg_cents,
    spl.sold_avg_cents
FROM pricing.sealed_price_latest spl
JOIN pricing.price_source ps ON ps.source_id = spl.source_id
JOIN pricing.transaction_type tt ON tt.transaction_type_id = spl.transaction_type_id
WHERE spl.product_id = $1
ORDER BY ps.code, tt.transaction_type_code
"""

_GET_SEALED_PRICE_HISTORY = """
SELECT
    po.ts_date,
    ps.code AS source,
    tt.transaction_type_code AS transaction_type,
    po.list_avg_cents,
    po.sold_avg_cents
FROM pricing.price_observation po
JOIN pricing.source_product sp ON sp.source_product_id = po.source_product_id
JOIN pricing.price_source ps ON ps.source_id = sp.source_id
JOIN pricing.sealed_products sep ON sep.product_id = sp.product_id
JOIN pricing.transaction_type tt ON tt.transaction_type_id = po.price_type_id
WHERE sep.mtgjson_uuid = $1
  AND po.ts_date >= $2
  AND po.ts_date <= $3
ORDER BY po.ts_date DESC, ps.code
"""

_UPSERT_SEALED_PRODUCTS = """
WITH game AS (
    SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg' LIMIT 1
),
set_lookup AS (
    SELECT set_id, set_code FROM card_catalog.sets WHERE lower(set_code) = lower($4)
),
ins_ref AS (
    INSERT INTO pricing.product_ref (game_id)
    SELECT game_id FROM game
    WHERE NOT EXISTS (
        SELECT 1 FROM pricing.sealed_products WHERE mtgjson_uuid = $1
    )
    RETURNING product_id
)
INSERT INTO pricing.sealed_products (product_id, set_id, name, product_type, mtgjson_uuid)
SELECT
    COALESCE(
        (SELECT product_id FROM ins_ref),
        (SELECT sp.product_id FROM pricing.sealed_products sp WHERE sp.mtgjson_uuid = $1)
    ),
    (SELECT set_id FROM set_lookup),
    $2,
    $3,
    $1
ON CONFLICT (mtgjson_uuid) DO UPDATE SET
    name         = EXCLUDED.name,
    product_type = EXCLUDED.product_type,
    set_id       = EXCLUDED.set_id,
    updated_at   = now()
"""

_GET_ALL_SEALED_UUIDS = """
SELECT mtgjson_uuid FROM pricing.sealed_products
"""


class SealedPricingRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "SealedPricingRepository"

    async def get_sealed_products_by_set(self, set_code: str) -> list[dict]:
        rows = await self.execute_query(_GET_SEALED_PRODUCTS_BY_SET, (set_code,))
        return [dict(r) for r in rows]

    async def get_sealed_prices_by_set(self, set_code: str) -> list[dict]:
        rows = await self.execute_query(_GET_SEALED_PRICES_BY_SET, (set_code,))
        return [dict(r) for r in rows]

    async def get_sealed_price_latest(self, product_id: UUID) -> list[dict]:
        rows = await self.execute_query(_GET_SEALED_PRICE_LATEST, (product_id,))
        return [dict(r) for r in rows]

    async def get_sealed_price_history(
        self,
        mtgjson_uuid: str,
        from_date: date,
        to_date: date,
    ) -> list[dict]:
        rows = await self.execute_query(
            _GET_SEALED_PRICE_HISTORY, (mtgjson_uuid, from_date, to_date)
        )
        return [dict(r) for r in rows]

    async def upsert_sealed_products(
        self, products: list[dict]
    ) -> int:
        """Upsert sealed product catalog rows. Each dict must have:
        mtgjson_uuid, name, product_type, set_code.
        Returns count of rows processed.
        """
        count = 0
        for p in products:
            await self.execute_command(
                _UPSERT_SEALED_PRODUCTS,
                (p["mtgjson_uuid"], p["name"], p["product_type"], p.get("set_code", "")),
            )
            count += 1
        return count

    async def fetch_all_sealed_uuids(self) -> set[str]:
        """Return all known sealed UUIDs for stream-routing decisions."""
        rows = await self.execute_query(_GET_ALL_SEALED_UUIDS, ())
        return {r["mtgjson_uuid"] for r in rows}

    async def copy_sealed_staging_batch(self, records: list[tuple]) -> int:
        """Bulk-load a batch of sealed price rows via asyncpg COPY."""
        if not records:
            return 0
        await self.execute_copy_records_to_table(
            "mtgjson_sealed_prices_staging",
            records=records,
            columns=(
                "sealed_uuid",
                "price_source",
                "price_type",
                "currency",
                "price_value",
                "price_date",
            ),
            schema_name="pricing",
        )
        return len(records)

    async def promote_sealed_staging(self, batch_days: int = 30) -> None:
        """Call the sealed promotion stored procedure."""
        await self.execute_procedure(
            "pricing.load_price_observation_from_mtgjson_sealed_staging",
            args=(batch_days,),
            timeout=14400,
        )

    async def truncate_sealed_staging(self) -> int:
        """Truncate any remaining unresolvable rows after promotion. Returns row count."""
        count = await self.execute_fetchval(
            "SELECT COUNT(*) FROM pricing.mtgjson_sealed_prices_staging"
        )
        if count:
            await self.execute_command("TRUNCATE pricing.mtgjson_sealed_prices_staging")
        return count or 0
```

- [ ] **Step 4: Run tests — should pass now (after applying migration to test container)**

The integration test runner applies all schema + migration files automatically. Confirm:

```bash
pytest tests/integration/services/sealed_pricing/ -v -m integration
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/pricing/sealed_pricing_repository.py \
        tests/integration/services/sealed_pricing/
git commit -m "feat(pricing): add SealedPricingRepository and promotion integration tests"
```

---

## Task 3: Service Steps (catalog bootstrap + stream routing + promote)

**Files:**
- Create: `src/automana/core/services/pricing/sealed_pricing_service.py`
- Modify: `src/automana/core/services/app_integration/mtgjson/data_loader.py`

- [ ] **Step 1: Write failing unit test for `stream_to_staging` sealed routing**

Create `tests/unit/services/__init__.py` (empty if missing).
Create `tests/unit/services/test_mtgjson_stream_routing.py`:

```python
"""Unit test: stream_to_staging routes sealed UUIDs to sealed staging."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_sealed_uuid_routed_to_sealed_staging():
    """A UUID that appears in the sealed set must go to copy_sealed_staging_batch,
    not copy_staging_batch (card staging)."""
    from automana.core.services.app_integration.mtgjson.data_loader import stream_to_staging

    sealed_uuid = "sealed-abc-123"
    card_uuid = "card-xyz-999"

    mock_mtgjson_repo = AsyncMock()
    mock_mtgjson_repo.acquire_streaming_lock = AsyncMock()
    mock_mtgjson_repo.copy_staging_batch = AsyncMock(return_value=1)

    mock_sealed_repo = AsyncMock()
    mock_sealed_repo.fetch_all_sealed_uuids = AsyncMock(return_value={sealed_uuid})
    mock_sealed_repo.copy_sealed_staging_batch = AsyncMock(return_value=1)

    mock_storage = AsyncMock()
    # Emit one sealed UUID entry and one card UUID entry
    mock_storage.iter_xz_json_kvitems = AsyncMock(
        return_value=_async_gen([
            (sealed_uuid, {"paper": {"tcgplayer": {"currency": "USD", "retail": {"foil": {"2026-03-01": 99.99}}}}}),
            (card_uuid,   {"paper": {"tcgplayer": {"currency": "USD", "retail": {"foil": {"2026-03-01": 1.50}}}}}),
        ])
    )

    await stream_to_staging(
        mtgjson_repository=mock_mtgjson_repo,
        sealed_repository=mock_sealed_repo,
        storage_service=mock_storage,
        file_path_prices="/tmp/fake.json.xz",
    )

    # Sealed UUID must go to sealed staging only
    mock_sealed_repo.copy_sealed_staging_batch.assert_called()
    # Card UUID must go to card staging only
    mock_mtgjson_repo.copy_staging_batch.assert_called()


async def _async_gen(items):
    for item in items:
        yield item
```

- [ ] **Step 2: Run — confirm it fails**

```bash
pytest tests/unit/services/test_mtgjson_stream_routing.py -v 2>&1 | head -20
```

Expected: FAIL — `stream_to_staging` does not accept `sealed_repository`.

- [ ] **Step 3: Write `sealed_pricing_service.py`**

```python
"""Pipeline service steps for sealed product pricing.

Three registered steps:
  pricing.sealed.bootstrap_catalog   — upsert sealed product catalog from MTGJson SealedProduct data
  pricing.sealed.promote_staging     — call promotion procedure
  pricing.sealed.cleanup_staging     — truncate unresolvable residue
"""
from __future__ import annotations

import logging

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.pricing.sealed_pricing_repository import SealedPricingRepository

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "pricing.sealed.bootstrap_catalog",
    db_repositories=["sealed_pricing"],
)
async def bootstrap_sealed_catalog(
    sealed_pricing_repository: SealedPricingRepository,
    sealed_products_data: list[dict],
) -> dict:
    """Upsert sealed product catalog rows from MTGJson SealedProduct data.

    Each element of ``sealed_products_data`` must contain:
      mtgjson_uuid, name, product_type, set_code

    Returns ``catalog_upserted`` for ops tracking.
    """
    logger.info("Bootstrapping sealed product catalog", extra={"count": len(sealed_products_data)})
    upserted = await sealed_pricing_repository.upsert_sealed_products(sealed_products_data)
    logger.info("Sealed catalog bootstrap complete", extra={"upserted": upserted})
    return {"catalog_upserted": upserted}


@ServiceRegistry.register(
    "pricing.sealed.promote_staging",
    db_repositories=["sealed_pricing"],
    runs_in_transaction=False,
    command_timeout=14400,
)
async def promote_sealed_staging(
    sealed_pricing_repository: SealedPricingRepository,
) -> dict:
    """Promote staged sealed rows into price_observation and sealed_price_latest."""
    logger.info("Promoting sealed staging to price observations")
    await sealed_pricing_repository.promote_sealed_staging()
    logger.info("Sealed staging promotion complete")
    return {}


@ServiceRegistry.register(
    "pricing.sealed.cleanup_staging",
    db_repositories=["sealed_pricing"],
)
async def cleanup_sealed_staging(
    sealed_pricing_repository: SealedPricingRepository,
) -> dict:
    """Truncate unresolvable rows remaining in mtgjson_sealed_prices_staging."""
    unresolved = await sealed_pricing_repository.truncate_sealed_staging()
    if unresolved:
        logger.warning(
            "Sealed staging cleanup: unresolved rows deleted",
            extra={"unresolved_rows": unresolved},
        )
    else:
        logger.info("Sealed staging cleanup: staging table is clean")
    return {"staging_rows_deleted": unresolved}
```

- [ ] **Step 4: Modify `stream_to_staging` in `data_loader.py` to accept and use `sealed_repository`**

The function signature changes from:

```python
@ServiceRegistry.register(
    "staging.mtgjson.stream_to_staging",
    db_repositories=["mtgjson"],
    storage_services=["mtgjson"],
)
async def stream_to_staging(
    mtgjson_repository: MtgjsonRepository,
    storage_service: StorageService,
    file_path_prices: str,
) -> dict:
```

To:

```python
@ServiceRegistry.register(
    "staging.mtgjson.stream_to_staging",
    db_repositories=["mtgjson", "sealed_pricing"],
    storage_services=["mtgjson"],
)
async def stream_to_staging(
    mtgjson_repository: MtgjsonRepository,
    sealed_pricing_repository,
    storage_service: StorageService,
    file_path_prices: str,
) -> dict:
```

Add the import at top of file:
```python
from automana.core.repositories.pricing.sealed_pricing_repository import SealedPricingRepository
```

Replace the streaming loop body. Old loop:

```python
    async for card_uuid, card in storage_service.iter_xz_json_kvitems(
        file_path_prices, prefix="data"
    ):
        cards_seen += 1
        batch.extend(_iter_card_rows(card_uuid, card))
        if len(batch) >= _COPY_BATCH_SIZE:
            total_rows += await mtgjson_repository.copy_staging_batch(batch)
            batch = []

    if batch:
        total_rows += await mtgjson_repository.copy_staging_batch(batch)
```

New loop (add variables `sealed_batch`, `sealed_uuids`, `sealed_rows` above the loop):

```python
    sealed_uuids: set[str] = await sealed_pricing_repository.fetch_all_sealed_uuids()
    logger.info("Sealed UUID set loaded", extra={"count": len(sealed_uuids)})

    batch: list[tuple] = []
    sealed_batch: list[tuple] = []
    total_rows = 0
    sealed_rows = 0
    cards_seen = 0

    async for uuid_key, entry in storage_service.iter_xz_json_kvitems(
        file_path_prices, prefix="data"
    ):
        cards_seen += 1
        if uuid_key in sealed_uuids:
            sealed_batch.extend(_iter_sealed_rows(uuid_key, entry))
            if len(sealed_batch) >= _COPY_BATCH_SIZE:
                sealed_rows += await sealed_pricing_repository.copy_sealed_staging_batch(sealed_batch)
                sealed_batch = []
        else:
            batch.extend(_iter_card_rows(uuid_key, entry))
            if len(batch) >= _COPY_BATCH_SIZE:
                total_rows += await mtgjson_repository.copy_staging_batch(batch)
                batch = []

    if batch:
        total_rows += await mtgjson_repository.copy_staging_batch(batch)
    if sealed_batch:
        sealed_rows += await sealed_pricing_repository.copy_sealed_staging_batch(sealed_batch)
```

Also update the return dict and log:

```python
    logger.info(
        "MTGJson streaming complete",
        extra={
            "cards": cards_seen,
            "rows_staged": total_rows,
            "sealed_rows_staged": sealed_rows,
            "file": file_path_prices,
        },
    )
    return {"rows_staged": total_rows, "cards_seen": cards_seen, "sealed_rows_staged": sealed_rows}
```

- [ ] **Step 5: Add `_iter_sealed_rows` helper in `data_loader.py`**

Add after the existing `_iter_card_rows` function:

```python
def _iter_sealed_rows(sealed_uuid: str, entry: Any) -> list[tuple]:
    """Fan out one MTGJson sealed entry into rows for the sealed staging table.

    MTGJson sealed product prices share the same nested shape as cards:
        entry.paper.<source>.<price_type>.<finish>.<date> = <price_float>
    We flatten to one row per (source, price_type, date) — finish is irrelevant
    for sealed products.
    """
    rows: list[tuple] = []
    if not isinstance(entry, dict):
        return rows
    paper = entry.get("paper")
    if not isinstance(paper, dict):
        return rows

    for source_name, source_val in paper.items():
        if not isinstance(source_val, dict):
            continue
        currency = source_val.get("currency") or "USD"
        for price_type, finishes in source_val.items():
            if price_type == "currency" or not isinstance(finishes, dict):
                continue
            for _finish, dates in finishes.items():
                if not isinstance(dates, dict):
                    continue
                for date_str, price_value in dates.items():
                    try:
                        price_date = date.fromisoformat(date_str)
                        price_float = float(price_value)
                    except (TypeError, ValueError):
                        continue
                    rows.append((
                        sealed_uuid,
                        source_name,
                        price_type,
                        currency,
                        price_float,
                        price_date,
                    ))
                    break  # one date entry per finish per price_type — first date wins
    return rows
```

- [ ] **Step 6: Run unit test — confirm it passes**

```bash
pytest tests/unit/services/test_mtgjson_stream_routing.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/automana/core/services/pricing/sealed_pricing_service.py \
        src/automana/core/services/app_integration/mtgjson/data_loader.py \
        tests/unit/services/test_mtgjson_stream_routing.py \
        tests/unit/services/__init__.py
git commit -m "feat(pricing): add sealed pipeline service steps and extend stream_to_staging routing"
```

---

## Task 4: Celery Pipeline Task

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`

- [ ] **Step 1: Add the sealed pipeline task**

Add after the existing `daily_mtgjson_data_pipeline` task:

```python
@shared_task(name="automana.worker.tasks.pipelines.daily_mtgjson_sealed_pipeline", bind=True)
def daily_mtgjson_sealed_pipeline(self):
    """Promote any staged sealed prices and refresh the sealed_price_latest snapshot.

    Expects sealed UUIDs to already exist in pricing.sealed_products (bootstrap_catalog
    must have been called at least once when new sets are added). The promotion
    procedure handles its own batching and commits.
    """
    set_task_id(self.request.id)
    run_key = f"mtgjson_sealed:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGJson sealed pricing pipeline", extra={"run_key": run_key})

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgjson_sealed",
                      source_name="mtgjson",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("pricing.sealed.promote_staging"),
        run_service.s("pricing.sealed.cleanup_staging"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id
```

- [ ] **Step 2: Verify the task is importable**

```bash
docker exec automana-celery-worker python -c \
    "from automana.worker.tasks.pipelines import daily_mtgjson_sealed_pipeline; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py
git commit -m "feat(worker): add daily_mtgjson_sealed_pipeline Celery task"
```

---

## Task 5: API Endpoints

**Files:**
- Create: `src/automana/api/routers/mtg/sealed_pricing.py`
- Modify: `src/automana/api/routers/mtg/__init__.py`
- Test: `tests/integration/api/test_sealed_pricing_router.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/api/test_sealed_pricing_router.py`:

```python
"""Integration test: sealed pricing API endpoints."""
from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.integration]


@pytest.fixture(scope="module")
async def seeded_sealed_set(db_pool):
    """Seed one sealed product with a price for API tests."""
    sealed_uuid = f"sealed-api-{uuid.uuid4().hex}"
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
            f"API Test Set {set_code}", set_code, set_type_id,
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
            f"API Booster Box {set_code}", "booster_box", sealed_uuid,
        )
        tcg_source_id = await conn.fetchval(
            "SELECT source_id FROM pricing.price_source WHERE code = 'tcg'"
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

    yield {"set_code": set_code, "product_id": product_id, "sealed_uuid": sealed_uuid}

    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.sealed_price_latest WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.sealed_products WHERE product_id = $1", product_id
        )
        await conn.execute(
            "DELETE FROM pricing.product_ref WHERE product_id = $1", product_id
        )
        await conn.execute("DELETE FROM card_catalog.sets WHERE set_id = $1", set_id)


async def test_get_sealed_prices_by_set_returns_200(client, seeded_sealed_set):
    set_code = seeded_sealed_set["set_code"]
    resp = await client.get(f"/api/catalog/mtg/sealed/{set_code}/prices")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "prices" in data
    assert len(data["prices"]) >= 1
    first = data["prices"][0]
    assert first["product_type"] == "booster_box"
    assert first["list_avg_cents"] == 9999


async def test_get_sealed_prices_unknown_set_returns_404(client):
    resp = await client.get("/api/catalog/mtg/sealed/ZZZNOPE/prices")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/integration/api/test_sealed_pricing_router.py -v -m integration 2>&1 | head -20
```

Expected: FAIL — `404 Not Found` (route doesn't exist yet).

- [ ] **Step 3: Write `sealed_pricing.py` router**

```python
"""Sealed product pricing API endpoints."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from automana.api.dependancies.service_deps import ServiceManagerDep

logger = logging.getLogger(__name__)

sealed_pricing_router = APIRouter(
    prefix="/sealed",
    tags=["Sealed Pricing"],
    responses={
        404: {"description": "Set not found"},
        500: {"description": "Internal server error"},
    },
)


class SealedPriceRow(BaseModel):
    product_id: str
    name: str
    product_type: str
    mtgjson_uuid: str
    source: str
    transaction_type: str
    price_date: Optional[date]
    list_low_cents: Optional[int]
    list_avg_cents: Optional[int]
    sold_avg_cents: Optional[int]


class SealedPricesResponse(BaseModel):
    set_code: str
    prices: list[SealedPriceRow]


class SealedPriceHistoryRow(BaseModel):
    ts_date: date
    source: str
    transaction_type: str
    list_avg_cents: Optional[int]
    sold_avg_cents: Optional[int]


class SealedPriceHistoryResponse(BaseModel):
    mtgjson_uuid: str
    history: list[SealedPriceHistoryRow]


@sealed_pricing_router.get(
    "/{set_code}/prices",
    summary="Current sealed product prices for a set",
    response_model=SealedPricesResponse,
    operation_id="sealed_prices_by_set",
)
async def get_sealed_prices_by_set(
    set_code: str,
    service_manager: ServiceManagerDep,
) -> SealedPricesResponse:
    rows = await service_manager.call(
        "pricing.sealed.get_prices_by_set",
        set_code=set_code,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No sealed products found for set '{set_code}'")
    return SealedPricesResponse(
        set_code=set_code.upper(),
        prices=[SealedPriceRow(**r) for r in rows],
    )


@sealed_pricing_router.get(
    "/{set_code}/{mtgjson_uuid}/history",
    summary="Daily price history for one sealed product",
    response_model=SealedPriceHistoryResponse,
    operation_id="sealed_price_history",
)
async def get_sealed_price_history(
    set_code: str,
    mtgjson_uuid: str,
    service_manager: ServiceManagerDep,
    from_date: Optional[date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[date] = Query(None, description="End date (inclusive)"),
    source: Optional[str] = Query(None, description="Filter by price source code"),
) -> SealedPriceHistoryResponse:
    rows = await service_manager.call(
        "pricing.sealed.get_price_history",
        mtgjson_uuid=mtgjson_uuid,
        from_date=from_date or date(2020, 1, 1),
        to_date=to_date or date.today(),
    )
    if source:
        rows = [r for r in rows if r["source"] == source]
    return SealedPriceHistoryResponse(
        mtgjson_uuid=mtgjson_uuid,
        history=[SealedPriceHistoryRow(**r) for r in rows],
    )
```

- [ ] **Step 4: Add two read service steps to `sealed_pricing_service.py`**

Append to the end of `sealed_pricing_service.py`:

```python
@ServiceRegistry.register(
    "pricing.sealed.get_prices_by_set",
    db_repositories=["sealed_pricing"],
)
async def get_sealed_prices_by_set(
    sealed_pricing_repository: SealedPricingRepository,
    set_code: str,
) -> list[dict]:
    return await sealed_pricing_repository.get_sealed_prices_by_set(set_code)


@ServiceRegistry.register(
    "pricing.sealed.get_price_history",
    db_repositories=["sealed_pricing"],
)
async def get_sealed_price_history(
    sealed_pricing_repository: SealedPricingRepository,
    mtgjson_uuid: str,
    from_date: date,
    to_date: date,
) -> list[dict]:
    return await sealed_pricing_repository.get_sealed_price_history(
        mtgjson_uuid, from_date, to_date
    )
```

Add `from datetime import date` at the top of `sealed_pricing_service.py`.

- [ ] **Step 5: Mount sealed_pricing_router in `mtg/__init__.py`**

Edit `src/automana/api/routers/mtg/__init__.py`:

```python
from fastapi import APIRouter
from automana.api.routers.mtg.card_reference import card_reference_router
from automana.api.routers.mtg.collection import router as collection_router
from automana.api.routers.mtg.set_reference import router as set_router
from automana.api.routers.mtg.sealed_pricing import sealed_pricing_router

mtg_router = APIRouter(prefix="/mtg")

mtg_router.include_router(card_reference_router)
mtg_router.include_router(collection_router)
mtg_router.include_router(set_router)
mtg_router.include_router(sealed_pricing_router)
```

- [ ] **Step 6: Register `sealed_pricing` repository alias in the ServiceManager or framework**

Check how repository names (`"pricing"`, `"mtgjson"`) are registered. Look at:
```bash
grep -r "sealed_pricing\|db_repositories" \
    src/automana/core/framework/ --include="*.py" | head -20
```

Add `"sealed_pricing"` → `SealedPricingRepository` to whatever registry or factory resolves those names. The exact file will be revealed by the grep above — follow the same pattern as the existing `"pricing"` entry.

- [ ] **Step 7: Run API integration tests — confirm they pass**

```bash
pytest tests/integration/api/test_sealed_pricing_router.py -v -m integration
```

Expected: both tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/automana/api/routers/mtg/sealed_pricing.py \
        src/automana/api/routers/mtg/__init__.py \
        src/automana/core/services/pricing/sealed_pricing_service.py \
        tests/integration/api/test_sealed_pricing_router.py
git commit -m "feat(api): add sealed pricing endpoints GET /sealed/{set_code}/prices and /history"
```

---

## Self-Review Notes

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `sealed_products` table | Task 1 |
| `sealed_price_latest` snapshot | Task 1 |
| `mtgjson_sealed_prices_staging` table | Task 1 |
| Promotion procedure | Task 1 |
| `SealedPricingRepository` | Task 2 |
| stream_to_staging routing | Task 3 |
| `bootstrap_sealed_catalog` service step | Task 3 |
| `promote_staged` + `cleanup` service steps | Task 3 |
| Celery pipeline task | Task 4 |
| `GET /sealed/{set_code}/prices` | Task 5 |
| `GET /sealed/{set_code}/{uuid}/history` | Task 5 |
| Grants to `app_celery`, `app_rw`, `app_ro` | Task 1 ✓ |
| Card pipeline untouched | stream_to_staging change is additive ✓ |

**One gap identified and addressed:** The repository alias `"sealed_pricing"` must be wired into the ServiceManager's repository factory — Task 5 Step 6 explicitly instructs the implementer to find and update that file rather than assuming its location.
