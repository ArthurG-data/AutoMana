-- =============================================================================
-- mtgjson_integrity_checks.sql
--
-- Purpose  : Structural orphan / loose-data checks for the MTGJson pipeline.
--            Covers pricing.data_provider, pricing.mtgjson_card_prices_staging,
--            pricing.mtgjson_staging (legacy), card_catalog.card_external_identifier,
--            ops.resources, and ops.ingestion_runs / ops.ingestion_run_steps.
--
-- How to run:
--   psql -U <role> -d automana -f mtgjson_integrity_checks.sql
--
-- Expected frequency : Daily (after mtgjson_daily pipeline completes)
--                      and on-demand.
--
-- Interpretation of severity:
--   'error' — FK-orphan or constraint-violation shape; should be 0 in a
--             healthy DB.
--   'warn'  — soft anomaly or reference-data gap; investigate but may be
--             benign depending on context.
--   'info'  — known-benign non-zero count; review but do not page.
--
-- IMPORTANT: None of these checks scan pricing.price_observation.
--            That hypertable causes DiskFullError under the 64 MB Docker
--            /dev/shm limit.  Use reltuples / pg_constraint / small-table
--            joins only.
--
-- Output shape (every block):
--   check_name TEXT, severity TEXT, row_count BIGINT, details JSONB
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- CHECK 01: pricing.data_provider row with code='mtgjson' must exist.
--           The promote_to_price_observation procedure raises an exception if
--           this row is missing.  bad_count=1 means missing (error).
-- ---------------------------------------------------------------------------
chk_01_data_provider_present AS (
    SELECT
        'data-provider-mtgjson-present'::TEXT             AS check_name,
        CASE WHEN EXISTS (
            SELECT 1 FROM pricing.data_provider WHERE code = 'mtgjson'
        ) THEN 0 ELSE 1 END::BIGINT                       AS bad_count,
        jsonb_build_object(
            'present', EXISTS (
                SELECT 1 FROM pricing.data_provider WHERE code = 'mtgjson'
            ),
            'all_providers', (
                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'data_provider_id', dp.data_provider_id,
                    'code', dp.code,
                    'description', dp.description
                )), '[]'::jsonb)
                FROM pricing.data_provider dp
            )
        ) AS details
),

-- ---------------------------------------------------------------------------
-- CHECK 02: Residual rows in pricing.mtgjson_card_prices_staging.
--           After promote_to_price_observation completes, staging is drained.
--           Large residuals indicate a crashed or skipped promotion step.
--           Uses reltuples (no scan) — fast safe estimate.
--           warn > 100 000, error > 1 000 000.
-- ---------------------------------------------------------------------------
chk_02_staging_residual AS (
    SELECT
        'mtgjson-staging-residual'::TEXT                  AS check_name,
        GREATEST(reltuples::bigint, 0)                   AS bad_count,
        jsonb_build_object(
            'estimated_rows', GREATEST(reltuples::bigint, 0),
            'note', 'fast estimate via pg_class.reltuples; run ANALYZE for precision'
        ) AS details
    FROM pg_class c
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    WHERE ns.nspname = 'pricing' AND c.relname = 'mtgjson_card_prices_staging'
),

-- ---------------------------------------------------------------------------
-- CHECK 03: Legacy pricing.mtgjson_staging should be empty.
--           This table predates the streaming refactor; new pipeline writes
--           go to mtgjson_card_prices_staging.  Non-zero rows indicate a
--           stale backfill or accidental re-activation of the old path.
--           Uses reltuples (no scan) — fast safe estimate.
-- ---------------------------------------------------------------------------
chk_03_legacy_staging AS (
    SELECT
        'mtgjson-legacy-staging-non-empty'::TEXT          AS check_name,
        GREATEST(reltuples::bigint, 0)                   AS bad_count,
        jsonb_build_object(
            'estimated_rows', GREATEST(reltuples::bigint, 0),
            'note', 'Legacy table — should be empty; non-zero means stale data from old pipeline path'
        ) AS details
    FROM pg_class c
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    WHERE ns.nspname = 'pricing' AND c.relname = 'mtgjson_staging'
),

-- ---------------------------------------------------------------------------
-- CHECK 04: card_catalog.card_external_identifier coverage for mtgjson_id.
--           The promote procedure resolves card_uuid via identifier_name='mtgjson_id'
--           (looked up via card_catalog.card_identifier_ref).
--           0 rows means the card catalog was never loaded with MTGJson UUIDs
--           — all promotions will fail.  Severity: error on 0, ok otherwise.
-- ---------------------------------------------------------------------------
chk_04_mtgjson_id_coverage AS (
    SELECT
        'mtgjson-id-coverage'::TEXT                       AS check_name,
        CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END::BIGINT AS bad_count,
        jsonb_build_object(
            'identifier_rows', COUNT(*),
            'note', 'Count of card_external_identifier rows for identifier_name=mtgjson_id'
        ) AS details
    FROM card_catalog.card_external_identifier cei
    JOIN card_catalog.card_identifier_ref cir
      ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
    WHERE cir.identifier_name = 'mtgjson_id'
),

-- ---------------------------------------------------------------------------
-- CHECK 05: ops.resources row with canonical_key='mtgjson.all_printings'
--           must exist.  The download step upserts a resource_version into
--           this resource; a missing row means the seeded ops schema is
--           incomplete.  bad_count=1 means missing (error).
-- ---------------------------------------------------------------------------
chk_05_resource_row_present AS (
    SELECT
        'mtgjson-resource-row-present'::TEXT              AS check_name,
        CASE WHEN EXISTS (
            SELECT 1 FROM ops.resources WHERE canonical_key = 'mtgjson.all_printings'
        ) THEN 0 ELSE 1 END::BIGINT                       AS bad_count,
        jsonb_build_object(
            'present', EXISTS (
                SELECT 1 FROM ops.resources WHERE canonical_key = 'mtgjson.all_printings'
            )
        ) AS details
),

-- ---------------------------------------------------------------------------
-- CHECK 06: mtgjson_daily runs stuck in 'running' status > 4 h.
--           A stale running row means a worker died without updating ops.
--           Severity: error if any stuck run exists.
-- ---------------------------------------------------------------------------
chk_06_stuck_pipeline_runs AS (
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
                WHERE pipeline_name = 'mtgjson_daily'
                  AND status = 'running'
                  AND started_at < now() - INTERVAL '4 hours'
                ORDER BY started_at
            ) s
        ) AS details
    FROM ops.ingestion_runs
    WHERE pipeline_name = 'mtgjson_daily'
      AND status = 'running'
      AND started_at < now() - INTERVAL '4 hours'
),

-- ---------------------------------------------------------------------------
-- CHECK 07: Failed steps in the most recent mtgjson_daily run.
--           Non-zero = the most recent run had at least one failed step.
--           Severity: error.
-- ---------------------------------------------------------------------------
chk_07_last_run_failed_steps AS (
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
                    WHERE pipeline_name = 'mtgjson_daily'
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                  AND irs2.status = 'failed'
            ) s
        ) AS details
    FROM ops.ingestion_run_steps irs
    WHERE irs.ingestion_run_id = (
        SELECT id FROM ops.ingestion_runs
        WHERE pipeline_name = 'mtgjson_daily'
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
            'data-provider-mtgjson-present',
            'mtgjson-id-coverage',
            'mtgjson-resource-row-present',
            'stuck-pipeline-runs',
            'last-run-failed-steps'
        ) THEN CASE WHEN bad_count > 0 THEN 'error' ELSE 'ok' END
        WHEN check_name = 'mtgjson-staging-residual'
            THEN CASE
                     WHEN bad_count > 1000000 THEN 'error'
                     WHEN bad_count > 100000  THEN 'warn'
                     ELSE 'ok'
                 END
        WHEN check_name = 'mtgjson-legacy-staging-non-empty'
            THEN CASE WHEN bad_count > 0 THEN 'warn' ELSE 'ok' END
        ELSE CASE WHEN bad_count > 0 THEN 'warn' ELSE 'ok' END
    END                                                   AS severity,
    bad_count                                             AS row_count,
    COALESCE(details, '[]'::jsonb)                        AS details
FROM (
    SELECT check_name, bad_count, details FROM chk_01_data_provider_present
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_02_staging_residual
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_03_legacy_staging
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_04_mtgjson_id_coverage
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_05_resource_row_present
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_06_stuck_pipeline_runs
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_07_last_run_failed_steps
) all_checks
;
-- No ORDER BY — the Python service layer partitions rows by severity
-- into errors/warnings/passed arrays.
