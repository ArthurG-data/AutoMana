-- =============================================================================
-- mtgjson_run_diff.sql
--
-- Purpose  : Post-run diff report for the mtgjson_daily pipeline.
--            Shows what changed during the most recent run: run metadata,
--            per-step status, batch-level counters from stream_to_staging and
--            promote_to_price_observation, staging residual (fast), and the
--            resource version consumed.
--
-- Pipeline : mtgjson_daily
-- Steps    : mtgjson.data.download.today
--            staging.mtgjson.stream_to_staging
--            staging.mtgjson.promote_to_price_observation
--            staging.mtgjson.cleanup_raw_files
--
-- How to run (latest run):
--   psql -U <role> -d automana -f mtgjson_run_diff.sql
--
-- To inspect a specific run, edit the WHERE clause in the `last_run` CTE:
--   Change: WHERE pipeline_name = 'mtgjson_daily' ... LIMIT 1
--   To:     WHERE id = 42
--
-- Output shape (all blocks):
--   check_name TEXT, severity TEXT, row_count BIGINT, details JSONB
--
-- Severity rules:
--   'error' — run failed, or a critical invariant is broken
--   'warn'  — partial success, zero rows promoted, or items_failed > 0
--   'info'  — informational; no action required
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- 0. Pin the run we're reporting on.
-- ---------------------------------------------------------------------------
last_run AS (
    SELECT
        id,
        run_key,
        pipeline_name,
        started_at,
        ended_at,
        status,
        current_step,
        progress,
        error_code,
        error_details,
        notes,
        EXTRACT(EPOCH FROM (COALESCE(ended_at, now()) - started_at)) AS duration_seconds
    FROM ops.ingestion_runs
    WHERE pipeline_name = 'mtgjson_daily'
    ORDER BY started_at DESC
    LIMIT 1
),

-- ---------------------------------------------------------------------------
-- 1. Run metadata — one row summarising the run itself.
-- ---------------------------------------------------------------------------
run_metadata AS (
    SELECT
        'run_metadata'::TEXT                              AS check_name,
        CASE
            WHEN COUNT(*) = 0                             THEN 'error'
            WHEN MAX(status) = 'failed'                   THEN 'error'
            WHEN MAX(status) IN ('partial', 'running')    THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(r))
            FROM (
                SELECT
                    lr.id,
                    lr.run_key,
                    lr.pipeline_name,
                    lr.started_at,
                    lr.ended_at,
                    lr.status,
                    lr.current_step,
                    lr.progress,
                    lr.error_code,
                    lr.error_details,
                    ROUND(lr.duration_seconds::numeric, 1) AS duration_seconds
                FROM last_run lr
            ) r
        )                                                 AS details
    FROM last_run
),

-- ---------------------------------------------------------------------------
-- 2. Per-step status from ops.ingestion_run_steps.
-- ---------------------------------------------------------------------------
step_status AS (
    SELECT
        'step_status'::TEXT                               AS check_name,
        CASE
            WHEN COUNT(*) FILTER (WHERE irs.status = 'failed')  > 0 THEN 'error'
            WHEN COUNT(*) FILTER (WHERE irs.status = 'partial') > 0 THEN 'warn'
            WHEN COUNT(*) FILTER (WHERE irs.status NOT IN ('success', 'failed', 'partial')) > 0 THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT
                    irs2.step_name,
                    irs2.status,
                    irs2.started_at,
                    irs2.ended_at,
                    ROUND(
                        EXTRACT(EPOCH FROM (COALESCE(irs2.ended_at, now()) - irs2.started_at))::numeric,
                        1
                    ) AS duration_seconds,
                    irs2.error_code,
                    irs2.error_details,
                    irs2.notes
                FROM ops.ingestion_run_steps irs2
                JOIN last_run lr ON irs2.ingestion_run_id = lr.id
                ORDER BY irs2.started_at
            ) s
        )                                                 AS details
    FROM ops.ingestion_run_steps irs
    JOIN last_run lr ON irs.ingestion_run_id = lr.id
),

-- ---------------------------------------------------------------------------
-- 3. Batch-step counters from ops.ingestion_step_batches.
--    MTGJson uses batches for stream_to_staging (date windows) and
--    promote_to_price_observation (batch_days windows).
--    items_failed > 0 → warn.
-- ---------------------------------------------------------------------------
batch_steps AS (
    SELECT
        'batch_steps'::TEXT                               AS check_name,
        CASE
            WHEN SUM(isb.items_failed) > 0                THEN 'warn'
            WHEN COUNT(*) = 0                             THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        jsonb_build_object(
            'total_batches',      COUNT(*),
            'total_items_ok',     SUM(isb.items_ok),
            'total_items_failed', SUM(isb.items_failed),
            'total_bytes_mb',     ROUND(SUM(isb.bytes_processed)::numeric / 1024 / 1024, 1),
            'total_duration_s',   ROUND(SUM(isb.duration_ms)::numeric / 1000, 1),
            'per_step', (
                SELECT jsonb_agg(to_jsonb(bs))
                FROM (
                    SELECT
                        irs2.step_name,
                        COUNT(isb2.id)                                          AS batches,
                        SUM(isb2.items_ok)                                      AS items_ok,
                        SUM(isb2.items_failed)                                  AS items_failed,
                        ROUND(SUM(isb2.bytes_processed)::numeric / 1024 / 1024, 1) AS mb,
                        ROUND(SUM(isb2.duration_ms)::numeric / 1000, 1)        AS duration_s,
                        COUNT(*) FILTER (WHERE isb2.status = 'failed')          AS failed_batches
                    FROM ops.ingestion_run_steps irs2
                    JOIN ops.ingestion_step_batches isb2 ON isb2.ingestion_run_step_id = irs2.id
                    JOIN last_run lr2 ON irs2.ingestion_run_id = lr2.id
                    GROUP BY irs2.step_name
                    ORDER BY irs2.step_name
                ) bs
            )
        )                                                 AS details
    FROM ops.ingestion_run_steps irs
    JOIN ops.ingestion_step_batches isb ON isb.ingestion_run_step_id = irs.id
    JOIN last_run lr ON irs.ingestion_run_id = lr.id
),

-- ---------------------------------------------------------------------------
-- 4. Staging residual — fast pg_class estimate.
--    After a successful promote_to_price_observation step, staging is drained.
--    Non-zero after a successful run indicates the cleanup step failed or was
--    skipped.  Large residuals (> 100 000) are warn.
-- ---------------------------------------------------------------------------
staging_residual AS (
    SELECT
        'staging_residual'::TEXT                          AS check_name,
        CASE
            WHEN GREATEST(reltuples::bigint, 0) > 1000000 THEN 'error'
            WHEN GREATEST(reltuples::bigint, 0) > 100000  THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        GREATEST(reltuples::bigint, 0)                   AS row_count,
        jsonb_build_object(
            'estimated_rows', GREATEST(reltuples::bigint, 0),
            'note', 'fast estimate via pg_class.reltuples; run ANALYZE for precision'
        )                                                 AS details
    FROM pg_class c
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    WHERE ns.nspname = 'pricing' AND c.relname = 'mtgjson_card_prices_staging'
),

-- ---------------------------------------------------------------------------
-- 5. Resource version consumed by the most recent run.
--    Links ops.ingestion_run_resources → ops.resource_versions → ops.resources
--    for the mtgjson.all_printings canonical key.
-- ---------------------------------------------------------------------------
download_resource AS (
    SELECT
        'download_resource'::TEXT                         AS check_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT COALESCE(jsonb_agg(to_jsonb(rv)), '[]'::jsonb)
            FROM (
                SELECT
                    r.canonical_key,
                    rv.download_uri,
                    rv.sha256,
                    rv.bytes        AS file_size_bytes,
                    rv.last_modified,
                    rv.status,
                    irr.status      AS run_status
                FROM ops.ingestion_run_resources irr
                JOIN ops.resource_versions rv ON rv.id = irr.resource_version_id
                JOIN ops.resources r ON r.id = rv.resource_id
                WHERE irr.ingestion_run_id = (SELECT id FROM last_run)
                  AND r.canonical_key = 'mtgjson.all_printings'
            ) rv
        )                                                 AS details
    FROM ops.ingestion_run_resources irr
    JOIN ops.resource_versions rv ON rv.id = irr.resource_version_id
    JOIN ops.resources r ON r.id = rv.resource_id
    WHERE irr.ingestion_run_id = (SELECT id FROM last_run)
      AND r.canonical_key = 'mtgjson.all_printings'
)

-- ---------------------------------------------------------------------------
-- Final UNION — all blocks produce the same shape.
-- ---------------------------------------------------------------------------
SELECT check_name, severity, row_count, details FROM run_metadata
UNION ALL
SELECT check_name, severity, row_count, details FROM step_status
UNION ALL
SELECT check_name, severity, row_count, details FROM batch_steps
UNION ALL
SELECT check_name, severity, row_count, details FROM staging_residual
UNION ALL
SELECT check_name, severity, row_count, details FROM download_resource
;
