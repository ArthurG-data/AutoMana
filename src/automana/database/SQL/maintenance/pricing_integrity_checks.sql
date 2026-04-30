-- =============================================================================
-- pricing_integrity_checks.sql
--
-- Purpose  : Structural orphan / loose-data checks for the pricing domain.
--            Covers source_product, product_ref, mtg_card_products,
--            price_observation, stg_price_observation, reject table, and the
--            seeded reference tables (card_finished, mtgstock_name_finish_suffix).
--
-- How to run:
--   psql -U <role> -d automana -f pricing_integrity_checks.sql
--
-- Expected frequency : Daily (after mtgStock_download_pipeline completes)
--                      and on-demand.
--
-- Interpretation of severity:
--   'error' — FK-orphan or constraint-violation shape; should be 0 in a
--             healthy DB.
--   'warn'  — soft anomaly or reference-data gap; investigate but may be
--             benign depending on context.
--   'info'  — known-benign non-zero count (e.g. open rejects during an
--             ongoing backfill); review but do not page.
--
-- Output shape (every block):
--   check_name TEXT, severity TEXT, row_count BIGINT, details JSONB
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- CHECK 01: source_product rows with no matching product_ref.
--           Foreign-key constraint should keep this at 0; non-zero means a
--           constraint was bypassed or a product_ref was deleted without
--           cascading.  Severity: error.
-- ---------------------------------------------------------------------------
chk_01_source_product_orphan AS (
    SELECT
        'source-product-orphan-product-ref'::TEXT         AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT sp.source_product_id, sp.product_id
                FROM pricing.source_product sp
                LEFT JOIN pricing.product_ref pr ON pr.product_id = sp.product_id
                WHERE pr.product_id IS NULL
                LIMIT 5
            ) s
        ) AS details
    FROM pricing.source_product sp
    LEFT JOIN pricing.product_ref pr ON pr.product_id = sp.product_id
    WHERE pr.product_id IS NULL
),

-- ---------------------------------------------------------------------------
-- CHECK 02: source_product rows with no matching price_source.
--           A source_product.source_id must reference a price_source row
--           (FK enforced). Non-zero = FK violation or stale reference.
--           Avoids scanning price_observation (hypertable shm pressure).
--           Severity: error.
-- ---------------------------------------------------------------------------
chk_02_source_product_no_price_source AS (
    SELECT
        'source-product-no-price-source'::TEXT            AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT sp.source_product_id, sp.source_id
                FROM pricing.source_product sp
                LEFT JOIN pricing.price_source ps ON ps.source_id = sp.source_id
                WHERE ps.source_id IS NULL
                LIMIT 5
            ) s
        ) AS details
    FROM pricing.source_product sp
    LEFT JOIN pricing.price_source ps ON ps.source_id = sp.source_id
    WHERE ps.source_id IS NULL
),

-- ---------------------------------------------------------------------------
-- CHECK 03: product_ref rows for the MTG game with no mtg_card_products row.
--           Every MTG product_ref must resolve to a card_version; a gap here
--           means the dimension load partially failed.  Severity: error.
-- ---------------------------------------------------------------------------
chk_03_product_ref_mtg_no_card AS (
    SELECT
        'product-ref-mtg-no-mtg-card-products'::TEXT      AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT pr.product_id
                FROM pricing.product_ref pr
                JOIN card_catalog.card_games_ref cgr ON cgr.game_id = pr.game_id
                WHERE cgr.code = 'mtg'
                  AND NOT EXISTS (
                      SELECT 1 FROM pricing.mtg_card_products mcp
                      WHERE mcp.product_id = pr.product_id
                  )
                LIMIT 5
            ) s
        ) AS details
    FROM pricing.product_ref pr
    JOIN card_catalog.card_games_ref cgr ON cgr.game_id = pr.game_id
    WHERE cgr.code = 'mtg'
      AND NOT EXISTS (
          SELECT 1 FROM pricing.mtg_card_products mcp
          WHERE mcp.product_id = pr.product_id
      )
),

-- ---------------------------------------------------------------------------
-- CHECK 04: Composite-PK constraint present on price_observation.
--           A full GROUP BY scan is too expensive on a compressed TimescaleDB
--           hypertable with 64 MB container shm. Instead, verify the PK
--           constraint exists in pg_constraint — if it is present, the DB
--           engine enforces uniqueness at write time.
--           bad_count = 0 means the constraint exists (healthy).
--           bad_count = 1 means the constraint is missing (error).
-- ---------------------------------------------------------------------------
chk_04_observation_pk_collision AS (
    SELECT
        'observation-pk-constraint-present'::TEXT         AS check_name,
        CASE WHEN EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class     t  ON t.oid  = c.conrelid
            JOIN pg_namespace ns ON ns.oid = t.relnamespace
            WHERE ns.nspname  = 'pricing'
              AND t.relname   = 'price_observation'
              AND c.contype   = 'p'  -- primary key
        ) THEN 0 ELSE 1 END::BIGINT                       AS bad_count,
        jsonb_build_object(
            'note', 'Verifies PK constraint exists; full duplicate scan skipped (hypertable shm pressure)',
            'constraint_present', EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class     t  ON t.oid  = c.conrelid
                JOIN pg_namespace ns ON ns.oid = t.relnamespace
                WHERE ns.nspname  = 'pricing'
                  AND t.relname   = 'price_observation'
                  AND c.contype   = 'p'
            )
        )                                                 AS details
),

-- ---------------------------------------------------------------------------
-- CHECK 05: Residual rows in stg_price_observation.
--           Stage 2 drains staging inline after each batch; this table should
--           be empty after a normal run.  Large residuals indicate a crashed
--           mid-batch restart or a skipped safety-net drain.
--           Severity: warn > 500 000, error > 5 000 000.
-- ---------------------------------------------------------------------------
chk_05_stg_residual AS (
    SELECT
        'stg-price-observation-residual'::TEXT            AS check_name,
        GREATEST(reltuples::bigint, 0)                   AS bad_count,
        jsonb_build_object(
            'estimated_rows', GREATEST(reltuples::bigint, 0),
            'note', 'fast estimate via pg_class.reltuples; run ANALYZE for precision'
        ) AS details
    FROM pg_class c
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    WHERE ns.nspname = 'pricing' AND c.relname = 'stg_price_observation'
),

-- ---------------------------------------------------------------------------
-- CHECK 06: Open (non-terminal) reject row count.
--           High counts during a fresh backfill are expected (~5.8 M after
--           historical load; target ~1.3 M after fixes 2+3).  Always 'info'.
-- ---------------------------------------------------------------------------
chk_06_reject_open_count AS (
    SELECT
        'reject-open-count'::TEXT                         AS check_name,
        COUNT(*) FILTER (WHERE NOT is_terminal)::BIGINT  AS bad_count,
        jsonb_build_object(
            'open',     COUNT(*) FILTER (WHERE NOT is_terminal),
            'terminal', COUNT(*) FILTER (WHERE is_terminal),
            'total',    COUNT(*)
        ) AS details
    FROM pricing.stg_price_observation_reject
),

-- ---------------------------------------------------------------------------
-- CHECK 07: Core card_finished codes (NONFOIL, FOIL, ETCHED) must be present.
--           Missing codes silently mis-classify observations.
--           row_count = number of missing required codes.  Severity: error.
-- ---------------------------------------------------------------------------
chk_07_card_finished_core_codes AS (
    SELECT
        'card-finished-core-codes'::TEXT                  AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        jsonb_build_object(
            'missing_codes', COALESCE(jsonb_agg(required.code), '[]'::jsonb)
        ) AS details
    FROM (VALUES ('NONFOIL'), ('FOIL'), ('ETCHED')) AS required(code)
    WHERE NOT EXISTS (
        SELECT 1 FROM pricing.card_finished cf WHERE cf.code = required.code
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 08: mtgstock_name_finish_suffix seed data count.
--           Migration 17 seeds exactly 6 rows; fewer rows indicate a partial
--           migration or accidental deletion.  Severity: warn on mismatch.
-- ---------------------------------------------------------------------------
chk_08_suffix_seed_count AS (
    SELECT
        'mtgstock-suffix-seed-count'::TEXT                AS check_name,
        CASE WHEN COUNT(*) < 6 THEN (6 - COUNT(*)) ELSE 0 END::BIGINT AS bad_count,
        jsonb_build_object(
            'actual_rows',   COUNT(*),
            'expected_rows', 6,
            'suffixes', COALESCE(
                (SELECT jsonb_agg(suffix ORDER BY suffix)
                 FROM pricing.mtgstock_name_finish_suffix),
                '[]'::jsonb
            )
        ) AS details
    FROM pricing.mtgstock_name_finish_suffix
),

-- ---------------------------------------------------------------------------
-- CHECK 09: mtgStock_download_pipeline runs stuck in 'running' status > 4 h.
--           A stale running row means a worker died without updating ops.
--           Severity: error if any stuck run exists.
-- ---------------------------------------------------------------------------
chk_09_stuck_pipeline_runs AS (
    SELECT
        'stuck-pipeline-runs'::TEXT                       AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT
                    id, run_key, started_at,
                    ROUND(EXTRACT(EPOCH FROM (now() - started_at)) / 3600.0, 1) AS hours_running,
                    current_step
                FROM ops.ingestion_runs
                WHERE pipeline_name = 'mtgStock_download_pipeline'
                  AND status = 'running'
                  AND started_at < now() - INTERVAL '4 hours'
                ORDER BY started_at
            ) s
        ) AS details
    FROM ops.ingestion_runs
    WHERE pipeline_name = 'mtgStock_download_pipeline'
      AND status = 'running'
      AND started_at < now() - INTERVAL '4 hours'
),

-- ---------------------------------------------------------------------------
-- CHECK 10: Failed steps in the most recent mtgStock_download_pipeline run.
--           Non-zero = the most recent run had at least one failed step.
--           Severity: error.
-- ---------------------------------------------------------------------------
chk_10_last_run_failed_steps AS (
    SELECT
        'last-run-failed-steps'::TEXT                     AS check_name,
        COUNT(*) FILTER (WHERE irs.status = 'failed')::BIGINT AS bad_count,
        (
            SELECT COALESCE(jsonb_agg(to_jsonb(s)), '[]'::jsonb)
            FROM (
                SELECT irs2.step_name, irs2.status, irs2.error_code, irs2.error_details
                FROM ops.ingestion_run_steps irs2
                WHERE irs2.ingestion_run_id = (
                    SELECT id FROM ops.ingestion_runs
                    WHERE pipeline_name = 'mtgStock_download_pipeline'
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                  AND irs2.status = 'failed'
            ) s
        ) AS details
    FROM ops.ingestion_run_steps irs
    WHERE irs.ingestion_run_id = (
        SELECT id FROM ops.ingestion_runs
        WHERE pipeline_name = 'mtgStock_download_pipeline'
        ORDER BY started_at DESC
        LIMIT 1
    )
)

-- ---------------------------------------------------------------------------
-- Final SELECT — severity is assigned here from the flat bad_count.
-- ---------------------------------------------------------------------------
SELECT
    check_name,
    CASE
        WHEN check_name IN (
            'source-product-orphan-product-ref',
            'source-product-no-price-source',
            'product-ref-mtg-no-mtg-card-products',
            'observation-pk-constraint-present',
            'card-finished-core-codes',
            'stuck-pipeline-runs',
            'last-run-failed-steps'
        ) THEN CASE WHEN bad_count > 0 THEN 'error' ELSE 'ok' END
        WHEN check_name = 'stg-price-observation-residual'
            THEN CASE
                     WHEN bad_count > 5000000 THEN 'error'
                     WHEN bad_count > 500000  THEN 'warn'
                     ELSE 'ok'
                 END
        WHEN check_name = 'reject-open-count'     THEN 'info'
        WHEN check_name = 'mtgstock-suffix-seed-count'
            THEN CASE WHEN bad_count > 0 THEN 'warn' ELSE 'ok' END
        ELSE CASE WHEN bad_count > 0 THEN 'warn' ELSE 'ok' END
    END                                                   AS severity,
    bad_count                                             AS row_count,
    COALESCE(details, '[]'::jsonb)                        AS details
FROM (
    SELECT check_name, bad_count, details FROM chk_01_source_product_orphan
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_02_source_product_no_price_source
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_03_product_ref_mtg_no_card
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_04_observation_pk_collision
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_05_stg_residual
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_06_reject_open_count
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_07_card_finished_core_codes
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_08_suffix_seed_count
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_09_stuck_pipeline_runs
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_10_last_run_failed_steps
) all_checks
;
-- No ORDER BY — the Python service layer partitions rows by severity
-- into errors/warnings/passed arrays.
