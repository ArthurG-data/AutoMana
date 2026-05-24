# MTGJson DFC UUID Resolution + Staging Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the 3,380 double-faced card (DFC) back-face UUIDs silently dropped per pipeline run, and prevent unresolved staging rows from accumulating indefinitely.

**Architecture:** A new `card_catalog.mtgjson_uuid_alias` table stores back-face UUIDs that collide with the existing `(card_version_id, card_identifier_ref_id)` primary key — no schema-wide PK change, no breakage of existing callers. The promotion stored procedure's `cv` CTE is extended to UNION in alias rows, making back-face prices resolvable. A new `staging.mtgjson.cleanup_staging_db` pipeline step truncates staging after promotion and logs any residual count as a warning.

**Tech Stack:** PostgreSQL 15 + TimescaleDB, asyncpg, Python 3.12, Celery, pytest + pytest-asyncio, `unittest.mock.AsyncMock`

---

## File Map

| Action | Path | What changes |
|--------|------|--------------|
| Create | `src/automana/database/SQL/migrations/migration_49_dfc_uuid_alias.sql` | New alias table + updated stored procedure |
| Modify | `src/automana/database/SQL/schemas/10_mtgjson_schema.sql` | Sync `cv` CTEs with migration so fresh rebuilds match |
| Modify | `src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py` | `upsert_mtgjson_id_mappings` alias fallback + new `truncate_staging_after_promotion` |
| Modify | `src/automana/core/services/app_integration/mtgjson/data_loader.py` | New `cleanup_staging_db` service |
| Modify | `src/automana/worker/tasks/pipelines.py` | Wire `staging.mtgjson.cleanup_staging_db` into chain |
| Modify | `src/automana/tools/tui/panels/celery.py` | Add new step to `daily_mtgjson_data_pipeline` KNOWN_TASKS entry |
| Create | `tests/unit/core/repositories/app_integration/mtgjson/test_mtgjson_repository.py` | Tests for alias insert + truncate |
| Modify | `tests/unit/core/services/mtgjson/test_data_loader.py` | Test for `cleanup_staging_db` |
| Modify | `tests/unit/worker/test_mtgjson_pipeline_wiring.py` | Update `EXPECTED_MTGJSON_STEPS` + new ordering assertion |

---

## Task 1: Create the migration

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_49_dfc_uuid_alias.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- migration_49_dfc_uuid_alias.sql
--
-- Adds card_catalog.mtgjson_uuid_alias to capture DFC back-face UUIDs that
-- collide with the (card_version_id, card_identifier_ref_id) PK in
-- card_external_identifier. The promotion procedure's cv CTE is extended to
-- UNION in alias rows so back-face prices resolve correctly.
BEGIN;

CREATE TABLE IF NOT EXISTS card_catalog.mtgjson_uuid_alias (
    uuid            TEXT        PRIMARY KEY,
    card_version_id UUID        NOT NULL REFERENCES card_catalog.card_version(card_version_id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mtgjson_uuid_alias_card_version
    ON card_catalog.mtgjson_uuid_alias (card_version_id);

GRANT SELECT, INSERT ON card_catalog.mtgjson_uuid_alias TO app_rw, app_admin, app_celery, app_backend;

-- Re-create the promotion procedure with the alias UNION in both cv CTEs.
CREATE OR REPLACE PROCEDURE pricing.load_price_observation_from_mtgjson_staging_batched(
   batch_days int DEFAULT 30
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_data_provider_id bigint;
  v_min date;
  v_max date;
  v_start date;
  v_end date;
  v_upserted bigint := 0;
  v_deleted  bigint := 0;
  v_total_upserted bigint := 0;
  v_total_deleted  bigint := 0;
  v_bootstrapped bigint := 0;
  v_is_ok boolean := false;
BEGIN
  IF batch_days IS NULL OR batch_days <= 0 THEN
    RAISE EXCEPTION 'batch_days must be > 0 (got %)', batch_days;
  END IF;

  -- Bootstrap: auto-create product_ref + mtg_card_products for any staged card
  -- that has a mtgjson_id (or alias) in the catalog but no product mapping yet.
  WITH unmapped AS (
    SELECT DISTINCT coalesce_cv.card_version_id
    FROM pricing.mtgjson_card_prices_staging st
    JOIN (
      SELECT cei.value AS uuid, cei.card_version_id
      FROM card_catalog.card_external_identifier cei
      JOIN card_catalog.card_identifier_ref cir
        ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
       AND cir.identifier_name = 'mtgjson_id'
      UNION ALL
      SELECT alias.uuid, alias.card_version_id
      FROM card_catalog.mtgjson_uuid_alias alias
    ) coalesce_cv ON coalesce_cv.uuid = st.card_uuid
    WHERE st.card_uuid IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM pricing.mtg_card_products mcp
        WHERE mcp.card_version_id = coalesce_cv.card_version_id
      )
  ),
  new_mapping AS (
    SELECT uuid_generate_v4() AS new_product_id, card_version_id
    FROM unmapped
  ),
  ins_ref AS (
    INSERT INTO pricing.product_ref (product_id, game_id)
    SELECT new_product_id, 1
    FROM new_mapping
  )
  INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
  SELECT new_product_id, card_version_id
  FROM new_mapping
  ON CONFLICT (card_version_id) DO NOTHING;

  GET DIAGNOSTICS v_bootstrapped = ROW_COUNT;
  IF v_bootstrapped > 0 THEN
    RAISE NOTICE 'Bootstrapped % card(s) into mtg_card_products (MTGJson-only source)', v_bootstrapped;
  END IF;
  COMMIT;

  -- normalize finish: map 'normal'→'NONFOIL' first, then uppercase everything
  UPDATE pricing.mtgjson_card_prices_staging
  SET finish_type = 'NONFOIL'
  WHERE lower(finish_type) = 'normal';

  UPDATE pricing.mtgjson_card_prices_staging
  SET finish_type = UPPER(finish_type)
  WHERE finish_type IS NOT NULL;

  -- normalize tcgplayer
  UPDATE pricing.mtgjson_card_prices_staging
  SET price_source = 'tcg'
  WHERE lower(price_source) = 'tcgplayer';

  -- normalize sell and buy (transaction_type_code)
  UPDATE pricing.mtgjson_card_prices_staging
  SET price_type = CASE
    WHEN lower(price_type) IN ('retail', 'market') THEN 'sell'
    WHEN lower(price_type) IN ('buylist', 'directlow') THEN 'buy'
    ELSE lower(price_type)
  END;

  -- provider
  SELECT dp.data_provider_id
  INTO v_data_provider_id
  FROM pricing.data_provider dp
  WHERE dp.code = 'mtgjson'
  LIMIT 1;

  IF v_data_provider_id IS NULL THEN
    RAISE EXCEPTION 'Missing pricing.data_provider row with code=mtgjson';
  END IF;

  -- staging span
  SELECT min(price_date)::date, max(price_date)::date
  INTO v_min, v_max
  FROM pricing.mtgjson_card_prices_staging
  WHERE price_date IS NOT NULL;

  IF v_min IS NULL THEN
    RAISE NOTICE 'No rows in pricing.mtgjson_card_prices_staging to process.';
    RETURN;
  END IF;

  v_start := v_min;

  WHILE v_start <= v_max LOOP
    v_end := (v_start + (batch_days - 1));

    BEGIN
      v_is_ok := false;
      -- upsert price sources for this batch
      INSERT INTO pricing.price_source (code, name, currency_code)
      SELECT DISTINCT s.price_source, s.price_source, s.currency
      FROM pricing.mtgjson_card_prices_staging s
      WHERE s.price_date::date BETWEEN v_start AND v_end
        AND s.price_source IS NOT NULL
        AND s.currency IS NOT NULL
      ON CONFLICT (code) DO NOTHING;

      -- upsert finishes for this batch
      INSERT INTO card_catalog.card_finished (code)
      SELECT DISTINCT UPPER(s.finish_type)
      FROM pricing.mtgjson_card_prices_staging s
      WHERE s.price_date::date BETWEEN v_start AND v_end
        AND s.finish_type IS NOT NULL
      ON CONFLICT (code) DO NOTHING;

      -- upsert observations
      WITH src AS (
        SELECT ps.source_id, ps.code, ps.name, ps.currency_code
        FROM pricing.price_source ps
      ),
      fin AS (
        SELECT cf.finish_id, cf.code
        FROM card_catalog.card_finished cf
      ),
      -- cv: primary mtgjson_id entries UNION back-face alias entries
      cv AS (
        SELECT cei.value::uuid AS card_uuid, cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
         AND cir.identifier_name = 'mtgjson_id'
        UNION ALL
        SELECT alias.uuid::uuid, alias.card_version_id
        FROM card_catalog.mtgjson_uuid_alias alias
      ),
      prod AS (
        SELECT cv.card_version_id, cv.card_uuid, mcp.product_id
        FROM cv
        JOIN pricing.mtg_card_products mcp
          ON mcp.card_version_id = cv.card_version_id
      ),
      pairs AS (
        SELECT DISTINCT p.product_id, s.source_id
        FROM pricing.mtgjson_card_prices_staging st
        JOIN src s ON s.code = st.price_source AND s.currency_code = st.currency
        JOIN prod p ON p.card_uuid::uuid = st.card_uuid::uuid
        WHERE st.price_date::date BETWEEN v_start AND v_end
          AND st.price_date IS NOT NULL
          AND st.card_uuid IS NOT NULL
          AND st.price_source IS NOT NULL
          AND st.currency IS NOT NULL
      ),
      insert_product_source AS (
        INSERT INTO pricing.source_product (product_id, source_id)
        SELECT product_id, source_id FROM pairs
        ON CONFLICT (product_id, source_id) DO UPDATE
          SET product_id = EXCLUDED.product_id
        RETURNING source_product_id, product_id, source_id
      ),
      staged AS (
        SELECT
          s.id,
          s.price_date::date AS ts_date,
          s.price_source,
          tt.transaction_type_id AS price_type_id,
          s.currency,
          s.finish_type,
          s.card_uuid,
          LEAST(round((s.price_value::numeric) * 100), 2147483647::numeric)::int AS price_cents
        FROM pricing.mtgjson_card_prices_staging s
        JOIN pricing.transaction_type tt ON tt.transaction_type_code = s.price_type
        WHERE s.price_date::date BETWEEN v_start AND v_end
          AND s.price_date IS NOT NULL
          AND s.card_uuid  IS NOT NULL
          AND s.price_source IS NOT NULL
          AND s.currency   IS NOT NULL
          AND s.finish_type IS NOT NULL
          AND s.price_value IS NOT NULL
      ),
      resolved AS (
        SELECT
          st.id,
          st.ts_date,
          fin.finish_id,
          pricing.default_condition_id() AS condition_id,
          card_catalog.default_language_id() AS language_id,
          st.price_cents,
          st.price_type_id,
          sp.source_id,
          sp.source_product_id
        FROM staged st
        JOIN src ON src.code = st.price_source AND src.currency_code = st.currency
        JOIN fin ON fin.code = st.finish_type
        JOIN prod ON prod.card_uuid::uuid = st.card_uuid::uuid
        JOIN insert_product_source sp
          ON sp.product_id = prod.product_id
         AND sp.source_id = src.source_id
      ),
      upserted AS (
        INSERT INTO pricing.price_observation (
          ts_date, price_type_id, finish_id, condition_id, language_id,
          list_low_cents, list_avg_cents, sold_avg_cents, list_count, sold_count,
          source_product_id, data_provider_id, scraped_at, created_at, updated_at
        )
        SELECT DISTINCT ON (r.ts_date, r.source_product_id, r.price_type_id, r.finish_id, r.condition_id, r.language_id)
          r.ts_date, r.price_type_id, r.finish_id, r.condition_id, r.language_id,
          NULL::int,
          CASE WHEN r.price_type_id = 1 THEN r.price_cents END::int,
          CASE WHEN r.price_type_id = 2 THEN r.price_cents END::int,
          CASE WHEN r.price_type_id = 1 THEN 1 END::int,
          CASE WHEN r.price_type_id = 2 THEN 1 END::int,
          r.source_product_id, v_data_provider_id, now(), now(), now()
        FROM resolved r
        ORDER BY r.ts_date, r.source_product_id, r.price_type_id, r.finish_id, r.condition_id, r.language_id
        ON CONFLICT (ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)
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

      -- delete resolved rows (same cv UNION including alias)
      WITH
      src AS (
        SELECT ps.source_id, ps.code, ps.currency_code FROM pricing.price_source ps
      ),
      fin AS (
        SELECT cf.finish_id, cf.code FROM card_catalog.card_finished cf
      ),
      cv AS (
        SELECT cei.value::uuid AS card_uuid, cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
         AND cir.identifier_name = 'mtgjson_id'
        UNION ALL
        SELECT alias.uuid::uuid, alias.card_version_id
        FROM card_catalog.mtgjson_uuid_alias alias
      ),
      prod AS (
        SELECT cv.card_version_id, cv.card_uuid, mcp.product_id
        FROM cv
        JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
      ),
      staged AS (
        SELECT s.id, s.price_source, s.currency, s.finish_type, s.card_uuid, s.price_type
        FROM pricing.mtgjson_card_prices_staging s
        WHERE s.price_date::date BETWEEN v_start AND v_end
          AND s.price_date IS NOT NULL
          AND s.card_uuid  IS NOT NULL
          AND s.price_source IS NOT NULL
          AND s.currency   IS NOT NULL
          AND s.finish_type IS NOT NULL
          AND s.price_value IS NOT NULL
      ),
      resolved_ids AS (
        SELECT st.id
        FROM staged st
        JOIN pricing.transaction_type tt ON tt.transaction_type_code = st.price_type
        JOIN src ON src.code = st.price_source AND src.currency_code = st.currency
        JOIN fin ON fin.code = st.finish_type
        JOIN prod ON prod.card_uuid::uuid = st.card_uuid::uuid
        JOIN pricing.source_product sp
          ON sp.product_id = prod.product_id
         AND sp.source_id  = src.source_id
      )
      DELETE FROM pricing.mtgjson_card_prices_staging s
      USING resolved_ids r
      WHERE s.id = r.id;

      GET DIAGNOSTICS v_deleted = ROW_COUNT;
      v_total_upserted := v_total_upserted + coalesce(v_upserted, 0);
      v_total_deleted  := v_total_deleted  + coalesce(v_deleted, 0);
      v_is_ok := true;
    EXCEPTION WHEN OTHERS THEN
      v_is_ok := false;
      RAISE;
    END;

    IF v_is_ok THEN
      RAISE NOTICE 'Batch % to %: upserted %, deleted %',
          v_start, v_end, v_upserted, v_deleted;
      COMMIT;
    END IF;
    v_start := v_end + 1;
  END LOOP;

  RAISE NOTICE 'Done. Total upserted %, total deleted %', v_total_upserted, v_total_deleted;
END;
$$;

COMMIT;
```

- [ ] **Step 2: Apply the migration**

```bash
docker exec automana-postgres-dev psql -U automana_admin -d automana \
  -f /workspaces/AutoMana/src/automana/database/SQL/migrations/migration_49_dfc_uuid_alias.sql
```

Expected: `BEGIN`, `CREATE TABLE`, `CREATE INDEX`, `GRANT`, `CREATE PROCEDURE`, `COMMIT` — no errors.

- [ ] **Step 3: Verify the table and procedure exist**

```bash
docker exec automana-postgres-dev psql -U automana_admin -d automana -c "
SELECT to_regclass('card_catalog.mtgjson_uuid_alias') AS alias_table;
SELECT proname FROM pg_proc WHERE proname = 'load_price_observation_from_mtgjson_staging_batched';"
```

Expected: `alias_table = card_catalog.mtgjson_uuid_alias`, `proname` row returned.

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_49_dfc_uuid_alias.sql
git commit -m "feat(db): add mtgjson_uuid_alias table and extend cv CTE for DFC back-face resolution"
```

---

## Task 2: Sync schema file with migration

**Files:**
- Modify: `src/automana/database/SQL/schemas/10_mtgjson_schema.sql`

The schema file is used for fresh DB builds (`--only rebuild`). It must match the procedure produced by the migration so they don't diverge.

- [ ] **Step 1: Replace both `cv` CTEs in `10_mtgjson_schema.sql`**

Find the first `cv` CTE (inside the INSERT section, around line 182). Replace:

```sql
      cv AS (
        SELECT
          cei.value::uuid AS card_uuid,
          cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = 'mtgjson_id'
      ),
```

With:

```sql
      -- cv: primary mtgjson_id entries UNION back-face alias entries
      cv AS (
        SELECT cei.value::uuid AS card_uuid, cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
         AND cir.identifier_name = 'mtgjson_id'
        UNION ALL
        SELECT alias.uuid::uuid, alias.card_version_id
        FROM card_catalog.mtgjson_uuid_alias alias
      ),
```

Find the second `cv` CTE (inside the DELETE section, around line 321). Replace:

```sql
      cv AS (
        SELECT
          cei.value::uuid AS card_uuid,
          cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = 'mtgjson_id'
      ),
```

With:

```sql
      -- cv: primary mtgjson_id entries UNION back-face alias entries
      cv AS (
        SELECT cei.value::uuid AS card_uuid, cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
         AND cir.identifier_name = 'mtgjson_id'
        UNION ALL
        SELECT alias.uuid::uuid, alias.card_version_id
        FROM card_catalog.mtgjson_uuid_alias alias
      ),
```

Also update the bootstrap `WITH unmapped AS (...)` block to also UNION alias rows (same pattern as in the migration above — replace the `JOIN card_catalog.card_external_identifier cei ... WHERE cir.identifier_name = 'mtgjson_id'` join with the UNION subquery).

- [ ] **Step 2: Commit**

```bash
git add src/automana/database/SQL/schemas/10_mtgjson_schema.sql
git commit -m "chore(db): sync schema file cv CTEs with migration_49 alias UNION"
```

---

## Task 3: Update repository — alias insert + truncate method

**Files:**
- Modify: `src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py`
- Create: `tests/unit/core/repositories/app_integration/mtgjson/test_mtgjson_repository.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/core/repositories/app_integration/mtgjson/test_mtgjson_repository.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from automana.core.repositories.app_integration.mtgjson.mtgjson_repository import MtgjsonRepository


def _make_repo() -> MtgjsonRepository:
    repo = MtgjsonRepository.__new__(MtgjsonRepository)
    repo.connection = MagicMock()
    return repo


class TestUpsertMtgjsonIdMappings:
    @pytest.mark.asyncio
    async def test_empty_pairs_returns_zero_without_db_call(self):
        repo = _make_repo()
        result = await repo.upsert_mtgjson_id_mappings([])
        assert result == 0
        repo.connection.fetchval.assert_not_called()

    @pytest.mark.asyncio
    async def test_primary_insert_count_returned(self):
        repo = _make_repo()
        repo.connection.fetchval = AsyncMock(return_value=2)
        repo.connection.execute = AsyncMock(return_value=None)

        result = await repo.upsert_mtgjson_id_mappings([
            ("uuid-front-1", "scryfall-1"),
            ("uuid-front-2", "scryfall-2"),
        ])

        assert result == 2
        repo.connection.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_alias_insert_called_after_primary(self):
        """alias insert must run after the primary insert, not before."""
        repo = _make_repo()
        call_order = []
        repo.connection.fetchval = AsyncMock(
            side_effect=lambda *a, **kw: call_order.append("fetchval") or 1
        )
        repo.connection.execute = AsyncMock(
            side_effect=lambda *a, **kw: call_order.append("execute")
        )

        await repo.upsert_mtgjson_id_mappings([("uuid-a", "scryfall-a")])

        assert call_order == ["fetchval", "execute"]

    @pytest.mark.asyncio
    async def test_alias_insert_receives_correct_arrays(self):
        repo = _make_repo()
        repo.connection.fetchval = AsyncMock(return_value=0)
        repo.connection.execute = AsyncMock(return_value=None)

        pairs = [("uuid-back-1", "scryfall-1"), ("uuid-back-2", "scryfall-2")]
        await repo.upsert_mtgjson_id_mappings(pairs)

        alias_call = repo.connection.execute.call_args
        _, args = alias_call[0][0], alias_call[0][1:]
        assert list(args[0]) == ["uuid-back-1", "uuid-back-2"]
        assert list(args[1]) == ["scryfall-1", "scryfall-2"]


class TestTruncateStagingAfterPromotion:
    @pytest.mark.asyncio
    async def test_returns_row_count_before_truncate(self):
        repo = _make_repo()
        repo.connection.fetchval = AsyncMock(return_value=42)
        repo.connection.execute = AsyncMock(return_value=None)

        result = await repo.truncate_staging_after_promotion()

        assert result == 42
        repo.connection.execute.assert_called_once_with(
            "TRUNCATE pricing.mtgjson_card_prices_staging"
        )

    @pytest.mark.asyncio
    async def test_returns_zero_and_skips_truncate_when_empty(self):
        repo = _make_repo()
        repo.connection.fetchval = AsyncMock(return_value=0)
        repo.connection.execute = AsyncMock(return_value=None)

        result = await repo.truncate_staging_after_promotion()

        assert result == 0
        repo.connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_count_treated_as_zero(self):
        repo = _make_repo()
        repo.connection.fetchval = AsyncMock(return_value=None)
        repo.connection.execute = AsyncMock(return_value=None)

        result = await repo.truncate_staging_after_promotion()

        assert result == 0
        repo.connection.execute.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana
.venv/bin/pytest tests/unit/core/repositories/app_integration/mtgjson/test_mtgjson_repository.py -v
```

Expected: `FAILED` — `truncate_staging_after_promotion` and the alias behaviour don't exist yet.

- [ ] **Step 3: Add `truncate_staging_after_promotion` and update `upsert_mtgjson_id_mappings`**

In `src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py`, replace the `upsert_mtgjson_id_mappings` method and add `truncate_staging_after_promotion` directly after it:

```python
    async def upsert_mtgjson_id_mappings(self, pairs: list[tuple[str, str]]) -> int:
        """Insert mtgjson_uuid → card_version_id rows into card_external_identifier.

        Accepts (mtgjson_uuid, scryfall_uuid) pairs from AllIdentifiers.json.
        Resolves card_version_id by joining via existing scryfall_id rows, then
        inserts with identifier_name='mtgjson_id'. Idempotent — the PK
        (card_version_id, card_identifier_ref_id) conflict is silently ignored.

        DFC back-face UUIDs that collide with the PK (same card_version_id already
        has a different mtgjson_id stored) are captured in
        card_catalog.mtgjson_uuid_alias so the promoter can resolve them too.

        Returns the number of rows inserted into card_external_identifier (0 on re-run).
        """
        if not pairs:
            return 0
        mtgjson_uuids = [p[0] for p in pairs]
        scryfall_uuids = [p[1] for p in pairs]
        count = await self.connection.fetchval("""
            WITH pairs AS (
                SELECT
                    unnest($1::text[]) AS mtgjson_uuid,
                    unnest($2::text[]) AS scryfall_uuid
            ),
            inserted AS (
                INSERT INTO card_catalog.card_external_identifier
                    (card_identifier_ref_id, card_version_id, value)
                SELECT
                    mtgjson_ref.card_identifier_ref_id,
                    scryfall_cei.card_version_id,
                    p.mtgjson_uuid
                FROM pairs p
                JOIN card_catalog.card_external_identifier scryfall_cei
                    ON scryfall_cei.value = p.scryfall_uuid
                JOIN card_catalog.card_identifier_ref scryfall_ref
                    ON scryfall_ref.card_identifier_ref_id = scryfall_cei.card_identifier_ref_id
                   AND scryfall_ref.identifier_name = 'scryfall_id'
                CROSS JOIN (
                    SELECT card_identifier_ref_id
                    FROM card_catalog.card_identifier_ref
                    WHERE identifier_name = 'mtgjson_id'
                ) mtgjson_ref
                ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING
                RETURNING 1
            )
            SELECT COUNT(*) FROM inserted
        """, mtgjson_uuids, scryfall_uuids)

        # Insert DFC back-face UUIDs that couldn't go into the primary table.
        # These are UUIDs whose scryfall_id resolves to a card_version_id that
        # already has a DIFFERENT mtgjson_id stored (the front-face UUID).
        await self.connection.execute("""
            INSERT INTO card_catalog.mtgjson_uuid_alias (uuid, card_version_id)
            SELECT p.mtgjson_uuid, scryfall_cei.card_version_id
            FROM (
                SELECT unnest($1::text[]) AS mtgjson_uuid,
                       unnest($2::text[]) AS scryfall_uuid
            ) p
            JOIN card_catalog.card_external_identifier scryfall_cei
                ON scryfall_cei.value = p.scryfall_uuid
            JOIN card_catalog.card_identifier_ref scryfall_ref
                ON scryfall_ref.card_identifier_ref_id = scryfall_cei.card_identifier_ref_id
               AND scryfall_ref.identifier_name = 'scryfall_id'
            WHERE NOT EXISTS (
                SELECT 1
                FROM card_catalog.card_external_identifier primary_cei
                JOIN card_catalog.card_identifier_ref primary_cir
                  ON primary_cir.card_identifier_ref_id = primary_cei.card_identifier_ref_id
                WHERE primary_cir.identifier_name = 'mtgjson_id'
                  AND primary_cei.value = p.mtgjson_uuid
            )
            ON CONFLICT (uuid) DO NOTHING
        """, mtgjson_uuids, scryfall_uuids)

        return count or 0

    async def truncate_staging_after_promotion(self) -> int:
        """Count and truncate any remaining rows in the staging table.

        Returns the number of rows deleted. Skips the TRUNCATE when the table
        is already empty to avoid an unnecessary DDL lock.
        """
        count = await self.connection.fetchval(
            "SELECT COUNT(*) FROM pricing.mtgjson_card_prices_staging"
        )
        if count:
            await self.connection.execute(
                "TRUNCATE pricing.mtgjson_card_prices_staging"
            )
        return count or 0
```

- [ ] **Step 4: Run tests — expect pass**

```bash
.venv/bin/pytest tests/unit/core/repositories/app_integration/mtgjson/test_mtgjson_repository.py -v
```

Expected: all 7 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/mtgjson/mtgjson_repository.py \
        tests/unit/core/repositories/app_integration/mtgjson/test_mtgjson_repository.py
git commit -m "feat(mtgjson): store DFC back-face UUIDs in alias table; add truncate_staging_after_promotion"
```

---

## Task 4: Add `cleanup_staging_db` service

**Files:**
- Modify: `src/automana/core/services/app_integration/mtgjson/data_loader.py`
- Modify: `tests/unit/core/services/mtgjson/test_data_loader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/core/services/mtgjson/test_data_loader.py`:

```python
@pytest.mark.asyncio
async def test_cleanup_staging_db_returns_deleted_count():
    from automana.core.services.app_integration.mtgjson.data_loader import cleanup_staging_db

    repo = MagicMock()
    repo.truncate_staging_after_promotion = AsyncMock(return_value=500)

    result = await cleanup_staging_db(mtgjson_repository=repo)

    repo.truncate_staging_after_promotion.assert_called_once()
    assert result == {"staging_rows_deleted": 500}


@pytest.mark.asyncio
async def test_cleanup_staging_db_zero_rows():
    from automana.core.services.app_integration.mtgjson.data_loader import cleanup_staging_db

    repo = MagicMock()
    repo.truncate_staging_after_promotion = AsyncMock(return_value=0)

    result = await cleanup_staging_db(mtgjson_repository=repo)

    assert result == {"staging_rows_deleted": 0}
```

- [ ] **Step 2: Run test to confirm failure**

```bash
.venv/bin/pytest tests/unit/core/services/mtgjson/test_data_loader.py -v -k "cleanup_staging"
```

Expected: `ImportError` or `FAILED` — `cleanup_staging_db` doesn't exist yet.

- [ ] **Step 3: Add the service to `data_loader.py`**

Append after `cleanup_raw_files` (end of file):

```python
@ServiceRegistry.register(
    "staging.mtgjson.cleanup_staging_db",
    db_repositories=["mtgjson"],
)
async def cleanup_staging_db(
    mtgjson_repository: MtgjsonRepository,
) -> dict:
    """Truncate any remaining rows from mtgjson_card_prices_staging after promotion.

    Rows that survive promotion are unresolvable (no catalog entry for their UUID).
    Logging them as a warning makes the residual visible in structured logs without
    failing the pipeline run.
    """
    unresolved = await mtgjson_repository.truncate_staging_after_promotion()
    if unresolved:
        logger.warning(
            "MTGJson staging cleanup: unresolved rows deleted",
            extra={"unresolved_rows": unresolved},
        )
    else:
        logger.info("MTGJson staging cleanup: staging table is clean")
    return {"staging_rows_deleted": unresolved}
```

- [ ] **Step 4: Run tests — expect pass**

```bash
.venv/bin/pytest tests/unit/core/services/mtgjson/test_data_loader.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/mtgjson/data_loader.py \
        tests/unit/core/services/mtgjson/test_data_loader.py
git commit -m "feat(mtgjson): add cleanup_staging_db service to truncate residual staging rows"
```

---

## Task 5: Wire cleanup step into pipeline + TUI

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`
- Modify: `src/automana/tools/tui/panels/celery.py`
- Modify: `tests/unit/worker/test_mtgjson_pipeline_wiring.py`

- [ ] **Step 1: Update `EXPECTED_MTGJSON_STEPS` in the test first (TDD)**

In `tests/unit/worker/test_mtgjson_pipeline_wiring.py`, update the list:

```python
EXPECTED_MTGJSON_STEPS = [
    "ops.pipeline_services.start_run",
    "mtgjson.data.download.all_identifiers",
    "staging.mtgjson.sync_uuid_mappings",
    "mtgjson.data.download.today",
    "staging.mtgjson.stream_to_staging",
    "staging.mtgjson.promote_to_price_observation",
    "staging.mtgjson.cleanup_staging_db",          # NEW
    "pricing.refresh_daily_prices",
    "card_catalog.card_search.refresh",
    "card_catalog.card_search.invalidate",
    "staging.mtgjson.cleanup_raw_files",
    "ops.pipeline_services.finish_run",
]
```

Also add a new ordering assertion:

```python
def test_cleanup_staging_db_runs_before_refresh_daily_prices(self):
    """DB staging cleanup must precede refresh_daily_prices so the price
    refresh never sees leftover rows from prior runs."""
    task = next(t for t in KNOWN_TASKS if t.name == "daily_mtgjson_data_pipeline")
    idx_cleanup = task.steps.index("staging.mtgjson.cleanup_staging_db")
    idx_refresh = task.steps.index("pricing.refresh_daily_prices")
    assert idx_cleanup < idx_refresh
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
.venv/bin/pytest tests/unit/worker/test_mtgjson_pipeline_wiring.py -v
```

Expected: `FAILED` — `staging.mtgjson.cleanup_staging_db` not in steps list.

- [ ] **Step 3: Update `daily_mtgjson_data_pipeline` in `pipelines.py`**

In `src/automana/worker/tasks/pipelines.py`, add the new step directly after `promote_to_price_observation`:

```python
        run_service.s("staging.mtgjson.promote_to_price_observation"),
        run_service.s("staging.mtgjson.cleanup_staging_db"),
        run_service.s("pricing.refresh_daily_prices"),
```

- [ ] **Step 4: Update `KNOWN_TASKS` in `celery.py`**

In `src/automana/tools/tui/panels/celery.py`, update the `daily_mtgjson_data_pipeline` entry:

```python
    CeleryTask(
        name="daily_mtgjson_data_pipeline",
        label="MTGJson daily pipeline",
        steps=[
            "ops.pipeline_services.start_run",
            "mtgjson.data.download.all_identifiers",
            "staging.mtgjson.sync_uuid_mappings",
            "mtgjson.data.download.today",
            "staging.mtgjson.stream_to_staging",
            "staging.mtgjson.promote_to_price_observation",
            "staging.mtgjson.cleanup_staging_db",
            "pricing.refresh_daily_prices",
            "card_catalog.card_search.refresh",
            "card_catalog.card_search.invalidate",
            "staging.mtgjson.cleanup_raw_files",
            "ops.pipeline_services.finish_run",
        ],
    ),
```

- [ ] **Step 5: Run tests — expect pass**

```bash
.venv/bin/pytest tests/unit/worker/test_mtgjson_pipeline_wiring.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Run full unit test suite to check for regressions**

```bash
.venv/bin/pytest tests/unit/ -x -q
```

Expected: all tests pass, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py \
        src/automana/tools/tui/panels/celery.py \
        tests/unit/worker/test_mtgjson_pipeline_wiring.py
git commit -m "feat(mtgjson): wire cleanup_staging_db into daily pipeline after promotion"
```

---

## Task 6: Smoke-test end-to-end (manual)

- [ ] **Step 1: Verify the alias table is empty before the run**

```bash
docker exec automana-postgres-dev psql -U automana_admin -d automana \
  -c "SELECT COUNT(*) FROM card_catalog.mtgjson_uuid_alias;"
```

Expected: `0` (freshly created by migration).

- [ ] **Step 2: Run `sync_uuid_mappings` manually to populate alias**

```bash
cd /home/arthur/projects/AutoMana
.venv/bin/automana-run staging.mtgjson.sync_uuid_mappings
```

Expected: JSON output with `mappings_inserted` (0 on re-run, non-zero first run). No errors.

- [ ] **Step 3: Verify alias rows were created**

```bash
docker exec automana-postgres-dev psql -U automana_admin -d automana \
  -c "SELECT COUNT(*) FROM card_catalog.mtgjson_uuid_alias;"
```

Expected: count ≈ 3,380 (the DFC back-face UUIDs).

- [ ] **Step 4: Run promotion against the existing file**

```bash
.venv/bin/automana-run staging.mtgjson.stream_to_staging \
  --file_path_prices /data/automana_data/mtgjson/raw/AllPricesToday_20260523_170334.json.xz
.venv/bin/automana-run staging.mtgjson.promote_to_price_observation
```

Expected: no errors. Check `NOTICE` output shows upserted/deleted counts that are higher than before.

- [ ] **Step 5: Run cleanup and verify staging is empty**

```bash
.venv/bin/automana-run staging.mtgjson.cleanup_staging_db
```

Expected: JSON output `{"staging_rows_deleted": N}` where N is close to 1,641 (the Scryfall-gap cards) × ~6 rows/card ≈ 9,800. Previously it was ~15,322.

```bash
docker exec automana-postgres-dev psql -U automana_admin -d automana \
  -c "SELECT COUNT(*) FROM pricing.mtgjson_card_prices_staging;"
```

Expected: `0`.

- [ ] **Step 6: Commit if any manual fixes were made; otherwise no commit needed**
