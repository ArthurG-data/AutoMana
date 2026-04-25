-- =============================================================================
-- scryfall_run_diff.sql
--
-- Purpose  : Post-run diff report for the scryfall_daily pipeline.
--            Shows what changed during the most recent (or a specified) run:
--            run metadata, per-step status, summary metrics, parsed step
--            counters, resource versions consumed, and heuristic row-level
--            "touched" counts in card_catalog.
--
-- How to run (latest run):
--   psql -U <role> -d automana -f scryfall_run_diff.sql
--
-- To inspect a specific run, edit the WHERE clause in the `last_run` CTE:
--   Change:  WHERE pipeline_name = 'scryfall_daily' ORDER BY started_at DESC LIMIT 1
--   To:      WHERE id = 42  (replace 42 with the desired ops.ingestion_runs.id)
--
-- Why a CTE instead of psql \set:
--   The backtick-execute form of \set is unreliable under ON_ERROR_STOP and
--   breaks when the script is run with -c or piped. The CTE approach is
--   self-contained, portable, and dry-run friendly.
--
-- Expected frequency : After every scryfall_daily run (or on-demand for
--                      incident investigation).
--
-- Interpretation     : severity='error' means something unexpected happened.
--                      severity='warn' means the run partially succeeded or
--                      a heuristic count looks off.  severity='info' is
--                      purely informational — review but do not page.
--
-- Output shape (all blocks):
--   check_name TEXT, severity TEXT, row_count BIGINT, details JSONB
--
-- NOTE on timestamp heuristics:
--   card_catalog.sets.updated_at         is DATE (day-precision). The upsert
--                                        calls DO UPDATE SET updated_at=NOW(),
--                                        so the count is a meaningful signal
--                                        at day granularity. The query filters
--                                        on updated_at.
--   card_catalog.card_version.updated_at is TIMESTAMPTZ, but the upsert uses
--                                        ON CONFLICT DO NOTHING — updated_at
--                                        is never refreshed on re-import.
--                                        The card_version and unique_cards_ref
--                                        heuristic queries filter on created_at
--                                        (first-insert time) because that is
--                                        the only column that changes under
--                                        ON CONFLICT DO NOTHING. Do not
--                                        interpret these counts as "cards updated"
--                                        — they count new cards added this run.
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- 0. Pin the run we're reporting on.
--    Edit the WHERE clause here to target a specific run_id.
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
    WHERE pipeline_name = 'scryfall_daily'
    ORDER BY started_at DESC
    LIMIT 1
),

-- ---------------------------------------------------------------------------
-- 1. Run metadata — one row summarising the run itself.
--    Non-zero row_count is always expected (1 = found, 0 = no run exists).
-- ---------------------------------------------------------------------------
run_metadata AS (
    SELECT
        'run_metadata'::TEXT                              AS check_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'error'
            WHEN MAX(status) IN ('failed')               THEN 'error'
            WHEN MAX(status) IN ('partial','running')    THEN 'warn'
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
                    lr.duration_seconds
                FROM last_run lr
                LIMIT 1
            ) r
        )                                                 AS details
    FROM last_run
),

-- ---------------------------------------------------------------------------
-- 2. Per-step status from ops.ingestion_run_steps.
--    Non-success steps indicate partial or failed runs.
--    row_count = total steps; details lists each step with timing.
-- ---------------------------------------------------------------------------
step_status AS (
    SELECT
        'step_status'::TEXT                               AS check_name,
        CASE
            WHEN COUNT(*) FILTER (WHERE irs.status = 'failed')  > 0 THEN 'error'
            WHEN COUNT(*) FILTER (WHERE irs.status = 'partial') > 0 THEN 'warn'
            WHEN COUNT(*) FILTER (WHERE irs.status NOT IN ('success','failed','partial')) > 0 THEN 'warn'
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
                    EXTRACT(EPOCH FROM (COALESCE(irs2.ended_at, now()) - irs2.started_at)) AS duration_seconds,
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
-- 3. Summary metrics from ops.ingestion_run_metrics.
--    row_count = number of distinct metric keys recorded for this run.
-- ---------------------------------------------------------------------------
run_metrics AS (
    SELECT
        'run_metrics'::TEXT                               AS check_name,
        CASE WHEN COUNT(*) = 0 THEN 'warn' ELSE 'info' END  AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(m))
            FROM (
                SELECT
                    irm2.metric_name,
                    irm2.metric_value_num,
                    irm2.metric_value_text,
                    irm2.recorded_at
                FROM ops.ingestion_run_metrics irm2
                JOIN last_run lr ON irm2.ingestion_run_id = lr.id
                ORDER BY irm2.metric_name
            ) m
        )                                                 AS details
    FROM ops.ingestion_run_metrics irm
    JOIN last_run lr ON irm.ingestion_run_id = lr.id
),

-- ---------------------------------------------------------------------------
-- 4. Parsed step counters from ops.ingestion_run_steps.notes.
--    Each step writes its ProcessingStats dict as a JSON string into notes.
--    We parse known keys: total_sets, successful_inserts, failed_inserts,
--    total_cards, skipped_inserts, batches_processed, success_rate.
--    Non-JSON notes (plain text) are safely ignored via the regex guard.
--    Rows with failed_inserts > 0 are flagged as warnings.
-- ---------------------------------------------------------------------------
step_counters AS (
    SELECT
        'step_counters'::TEXT                             AS check_name,
        CASE
            WHEN SUM(
                CASE WHEN (CASE WHEN irs.notes ~ '^\s*\{' THEN irs.notes::jsonb END ->> 'failed_inserts')::numeric > 0 THEN 1 ELSE 0 END
            ) > 0 THEN 'warn'
            ELSE 'info'
        END                                               AS severity,
        COUNT(*) FILTER (WHERE irs.notes ~ '^\s*\{')::BIGINT  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(sc))
            FROM (
                SELECT
                    irs2.step_name,
                    CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END          AS raw_notes,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'total_sets')::numeric            AS total_sets,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'successful_inserts')::numeric    AS successful_inserts,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'failed_inserts')::numeric        AS failed_inserts,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'total_cards')::numeric           AS total_cards,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'skipped_inserts')::numeric       AS skipped_inserts,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'batches_processed')::numeric     AS batches_processed,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'success_rate')::numeric          AS success_rate,
                    (CASE WHEN irs2.notes ~ '^\s*\{' THEN irs2.notes::jsonb END ->> 'duration_seconds')::numeric      AS duration_seconds
                FROM ops.ingestion_run_steps irs2
                JOIN last_run lr ON irs2.ingestion_run_id = lr.id
                WHERE irs2.notes ~ '^\s*\{'
                ORDER BY irs2.started_at
            ) sc
        )                                                 AS details
    FROM ops.ingestion_run_steps irs
    JOIN last_run lr ON irs.ingestion_run_id = lr.id
),

-- ---------------------------------------------------------------------------
-- 5. Resource versions consumed by this run.
--    Links ops.ingestion_run_resources → ops.resource_versions → ops.resources.
-- ---------------------------------------------------------------------------
run_resources AS (
    SELECT
        'run_resources'::TEXT                             AS check_name,
        CASE WHEN COUNT(*) = 0 THEN 'warn' ELSE 'info' END  AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(rv))
            FROM (
                SELECT
                    res.name          AS resource_name,
                    res.external_type,
                    res.canonical_key,
                    rv2.download_uri,
                    rv2.bytes,
                    rv2.status        AS resource_status,
                    rv2.created_at    AS downloaded_at,
                    irr2.status       AS run_resource_status,
                    irr2.notes        AS run_resource_notes
                FROM ops.ingestion_run_resources irr2
                JOIN last_run lr ON irr2.ingestion_run_id = lr.id
                JOIN ops.resource_versions rv2 ON irr2.resource_version_id = rv2.id
                JOIN ops.resources res ON rv2.resource_id = res.id
                ORDER BY rv2.created_at
            ) rv
        )                                                 AS details
    FROM ops.ingestion_run_resources irr
    JOIN last_run lr ON irr.ingestion_run_id = lr.id
),

-- ---------------------------------------------------------------------------
-- 6a. Heuristic: sets "touched" during this run.
--     card_catalog.sets.updated_at is DATE — comparison uses date cast.
--     Upserts DO refresh updated_at here, so this is a reasonable signal.
-- ---------------------------------------------------------------------------
sets_touched AS (
    SELECT
        'sets_touched_heuristic'::TEXT                    AS check_name,
        'info'::TEXT                                      AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(st))
            FROM (
                SELECT s2.set_id, s2.set_code, s2.set_name, s2.updated_at
                FROM card_catalog.sets s2
                JOIN last_run lr ON
                    s2.updated_at >= lr.started_at::date
                    AND s2.updated_at <= COALESCE(lr.ended_at, now())::date
                ORDER BY s2.updated_at DESC
                LIMIT 5
            ) st
        )                                                 AS details
    FROM card_catalog.sets s
    JOIN last_run lr ON
        s.updated_at >= lr.started_at::date
        AND s.updated_at <= COALESCE(lr.ended_at, now())::date
),

-- ---------------------------------------------------------------------------
-- 6b. Heuristic: card_versions created during this run.
--     ON CONFLICT DO NOTHING — updated_at = first-insert only.
--     This count is new cards, not updated cards.
-- ---------------------------------------------------------------------------
card_versions_created AS (
    SELECT
        'card_versions_created_heuristic'::TEXT           AS check_name,
        'info'::TEXT                                      AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(cv2))
            FROM (
                SELECT cv3.card_version_id, cv3.set_id, cv3.created_at
                FROM card_catalog.card_version cv3
                JOIN last_run lr ON
                    cv3.created_at >= lr.started_at
                    AND cv3.created_at <= COALESCE(lr.ended_at, now())
                ORDER BY cv3.created_at DESC
                LIMIT 5
            ) cv2
        )                                                 AS details
    FROM card_catalog.card_version cv
    JOIN last_run lr ON
        cv.created_at >= lr.started_at
        AND cv.created_at <= COALESCE(lr.ended_at, now())
),

-- ---------------------------------------------------------------------------
-- 6c. Heuristic: unique_cards_ref created during this run.
--     Same ON CONFLICT DO NOTHING caveat as card_version.
-- ---------------------------------------------------------------------------
unique_cards_created AS (
    SELECT
        'unique_cards_created_heuristic'::TEXT            AS check_name,
        'info'::TEXT                                      AS severity,
        COUNT(*)::BIGINT                                  AS row_count,
        (
            SELECT jsonb_agg(to_jsonb(uc2))
            FROM (
                SELECT ucr2.unique_card_id, ucr2.card_name, ucr2.created_at
                FROM card_catalog.unique_cards_ref ucr2
                JOIN last_run lr ON
                    ucr2.created_at >= lr.started_at
                    AND ucr2.created_at <= COALESCE(lr.ended_at, now())
                ORDER BY ucr2.created_at DESC
                LIMIT 5
            ) uc2
        )                                                 AS details
    FROM card_catalog.unique_cards_ref ucr
    JOIN last_run lr ON
        ucr.created_at >= lr.started_at
        AND ucr.created_at <= COALESCE(lr.ended_at, now())
)

-- ---------------------------------------------------------------------------
-- Final UNION — all blocks produce the same shape.
-- ---------------------------------------------------------------------------
SELECT check_name, severity, row_count, details FROM run_metadata
UNION ALL
SELECT check_name, severity, row_count, details FROM step_status
UNION ALL
SELECT check_name, severity, row_count, details FROM run_metrics
UNION ALL
SELECT check_name, severity, row_count, details FROM step_counters
UNION ALL
SELECT check_name, severity, row_count, details FROM run_resources
UNION ALL
SELECT check_name, severity, row_count, details FROM sets_touched
UNION ALL
SELECT check_name, severity, row_count, details FROM card_versions_created
UNION ALL
SELECT check_name, severity, row_count, details FROM unique_cards_created
;
