-- =============================================================================
-- pricing_run_diff.sql
--
-- Purpose  : Post-run diff report for the mtgStock_download_pipeline.
--            Shows what changed during the most recent run: run metadata,
--            per-step status, batch-level counters from bulk_load and
--            raw_to_staging, reject table summary, rows promoted to
--            price_observation, and current hypertable size heuristic.
--
-- Pipeline : mtgStock_download_pipeline
-- Steps    : bulk_load, raw_to_staging, retry_rejects, staging_to_prices
--
-- How to run (latest run):
--   psql -U <role> -d automana -f pricing_run_diff.sql
--
-- To inspect a specific run, edit the WHERE clause in the `last_run` CTE:
--   Change: WHERE pipeline_name = 'mtgStock_download_pipeline' ... LIMIT 1
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
    WHERE pipeline_name = 'mtgStock_download_pipeline'
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
--    Each batch = one folder-window in bulk_load or one 30-day window in
--    raw_to_staging.  items_failed > 0 → warn.
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
-- 4. Reject table summary: open vs terminal counts + top reject reasons.
--    row_count = open (unresolved) rejects.
--    Thresholds reflect expected post-backfill state (~5.8 M open rejects on
--    first build; should converge toward ~1.3 M after fix 2+3 are applied).
-- ---------------------------------------------------------------------------
reject_summary AS (
    SELECT
        'reject_summary'::TEXT                            AS check_name,
        CASE
            WHEN COUNT(*) FILTER (WHERE NOT r.is_terminal) > 10000000 THEN 'error'
            WHEN COUNT(*) FILTER (WHERE NOT r.is_terminal) > 2000000  THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        COUNT(*) FILTER (WHERE NOT r.is_terminal)::BIGINT AS row_count,
        jsonb_build_object(
            'open',     COUNT(*) FILTER (WHERE NOT r.is_terminal),
            'terminal', COUNT(*) FILTER (WHERE r.is_terminal),
            'total',    COUNT(*),
            'top_reject_reasons', (
                SELECT jsonb_agg(to_jsonb(rr))
                FROM (
                    SELECT r2.reject_reason, COUNT(*) AS cnt
                    FROM pricing.stg_price_observation_reject r2
                    WHERE NOT r2.is_terminal
                    GROUP BY r2.reject_reason
                    ORDER BY cnt DESC
                    LIMIT 5
                ) rr
            ),
            'top_terminal_reasons', (
                SELECT jsonb_agg(to_jsonb(tr))
                FROM (
                    SELECT r2.terminal_reason, COUNT(*) AS cnt
                    FROM pricing.stg_price_observation_reject r2
                    WHERE r2.is_terminal
                    GROUP BY r2.terminal_reason
                    ORDER BY cnt DESC
                    LIMIT 5
                ) tr
            )
        )                                                 AS details
    FROM pricing.stg_price_observation_reject r
),

-- ---------------------------------------------------------------------------
-- 5. Rows promoted to price_observation during the run window.
--    Filtered on scraped_at (set by bulk_load at ingestion time).
--    row_count = 0 on a daily non-backfill run is normal because daily runs
--    only load new price points for existing prints; but 0 after a full
--    historical load would indicate the promotion step failed.
-- ---------------------------------------------------------------------------
recent_promotion AS (
    SELECT
        'recent_promotion'::TEXT                          AS check_name,
        CASE
            WHEN COUNT(*) = 0 AND (SELECT MAX(status) FROM last_run) = 'success' THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        jsonb_build_object(
            'promoted_rows',      COUNT(*),
            'distinct_products',  COUNT(DISTINCT po.source_product_id),
            'min_ts_date',        MIN(po.ts_date),
            'max_ts_date',        MAX(po.ts_date),
            'run_started_at',     (SELECT lr.started_at FROM last_run lr),
            'run_ended_at',       (SELECT lr.ended_at   FROM last_run lr)
        )                                                 AS details
    FROM pricing.price_observation po
    JOIN last_run lr ON
        po.scraped_at >= lr.started_at
        AND po.scraped_at <= COALESCE(lr.ended_at, now())
),

-- ---------------------------------------------------------------------------
-- 6. Total price_observation volume (fast estimate via pg_class.reltuples).
--    row_count < 1 000 on a DB that has run the backfill → warn.
-- ---------------------------------------------------------------------------
observation_volume AS (
    SELECT
        'observation_volume'::TEXT                        AS check_name,
        CASE
            WHEN GREATEST(reltuples::bigint, 0) < 1000    THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        GREATEST(reltuples::bigint, 0)                   AS row_count,
        jsonb_build_object(
            'estimated_rows',  GREATEST(reltuples::bigint, 0),
            'note', 'fast estimate via pg_class.reltuples; run ANALYZE for precision'
        )                                                 AS details
    FROM pg_class c
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    WHERE ns.nspname = 'pricing' AND c.relname = 'price_observation'
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
SELECT check_name, severity, row_count, details FROM reject_summary
UNION ALL
SELECT check_name, severity, row_count, details FROM recent_promotion
UNION ALL
SELECT check_name, severity, row_count, details FROM observation_volume
;
