-- Migration 19: Fix pricing.archive_to_weekly — "tuple decompression limit exceeded"
--
-- Root cause: print_price_daily is a TimescaleDB hypertable with a 30-day
-- compression policy. The DELETE step inside each batch issues row-level DML
-- against already-compressed chunks, which forces inline decompression. The
-- default timescaledb.max_tuples_decompressed_per_dml_transaction (~100,000)
-- is far below the ~5M rows per batch window, causing the procedure to abort.
--
-- Fix:
--   1. Explicitly decompress each chunk overlapping the batch window before
--      the DELETE so the DML runs against uncompressed rows (no GUC issue).
--      decompress_chunk(..., if_compressed => TRUE) is a no-op on already-
--      uncompressed chunks, making the procedure safe to run regardless of
--      compression state. The compression policy re-compresses the data
--      naturally on its next scheduled run.
--   2. Reduce batch size from the previous values (2 days or 4 weeks) to
--      7 days — one full chunk per batch — to bound memory and lock duration.
--
-- Safe to apply: only replaces the stored procedure, no DDL on tables.

CREATE OR REPLACE PROCEDURE pricing.archive_to_weekly(
    p_older_than INTERVAL DEFAULT '5 years'
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_cutoff        DATE;
    v_min_date      DATE;
    v_max_date      DATE;
    v_start         DATE;
    v_end           DATE;
    v_batch_days    INT  := 7;    -- one 7-day chunk per batch
    v_ok            BOOLEAN;
    _chunk          REGCLASS;
    cur_archived    BIGINT;
    cur_deleted     BIGINT;
    total_archived  BIGINT := 0;
    total_deleted   BIGINT := 0;
BEGIN
    -- Cutoff is floored to the previous Monday so we always archive complete weeks.
    v_cutoff := DATE_TRUNC('week', CURRENT_DATE - p_older_than)::DATE;

    SELECT MIN(price_date), MAX(price_date)
    INTO   v_min_date, v_max_date
    FROM   pricing.print_price_daily
    WHERE  price_date < v_cutoff;

    IF v_min_date IS NULL THEN
        RAISE NOTICE 'archive_to_weekly: no data older than % to archive', v_cutoff;
        RETURN;
    END IF;

    RAISE NOTICE 'archive_to_weekly: archiving % to % (cutoff=%, older_than=%)',
                 v_min_date, v_max_date, v_cutoff, p_older_than;

    v_start := DATE_TRUNC('week', v_min_date)::DATE;

    WHILE v_start < v_cutoff LOOP
        v_end := LEAST(v_start + (v_batch_days - 1), v_cutoff - 1);
        v_ok  := FALSE;

        BEGIN
            SET LOCAL work_mem             = '256MB';
            SET LOCAL maintenance_work_mem = '512MB';
            SET LOCAL synchronous_commit   = off;
            -- 0 = unlimited; required so decompress_chunk() on large chunks succeeds.
            SET LOCAL timescaledb.max_tuples_decompressed_per_dml_transaction = 0;

            -- Decompress every chunk that overlaps this batch window before any DML.
            -- This avoids "tuple decompression limit exceeded" on the DELETE step.
            -- if_compressed => TRUE makes this a no-op on already-uncompressed chunks.
            FOR _chunk IN
                SELECT show_chunks(
                    'pricing.print_price_daily',
                    older_than => v_end + 1,
                    newer_than => v_start
                )
            LOOP
                PERFORM decompress_chunk(_chunk, if_compressed => TRUE);
            END LOOP;

            -- Aggregate tier 2 → tier 3 for this batch window.
            DROP TABLE IF EXISTS _weekly_batch;
            CREATE TEMP TABLE _weekly_batch ON COMMIT DROP AS
            SELECT
                DATE_TRUNC('week', price_date)::DATE         AS price_week,
                card_version_id,
                source_id,
                transaction_type_id,
                finish_id,
                condition_id,
                language_id,
                MIN(list_low_cents)::INTEGER                 AS list_low_cents,
                AVG(list_avg_cents)::INTEGER                 AS list_avg_cents,
                AVG(sold_avg_cents)::INTEGER                 AS sold_avg_cents,
                COUNT(DISTINCT price_date)::SMALLINT         AS n_days,
                MAX(n_providers)::SMALLINT                   AS n_providers
            FROM  pricing.print_price_daily
            WHERE price_date >= v_start
              AND price_date <= v_end
            GROUP BY
                DATE_TRUNC('week', price_date),
                card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id;

            -- Upsert into print_price_weekly (idempotent re-runs are safe).
            INSERT INTO pricing.print_price_weekly (
                price_week, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_days, n_providers
            )
            SELECT
                price_week, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_days, n_providers
            FROM _weekly_batch
            ON CONFLICT (price_week, card_version_id, source_id,
                         transaction_type_id, finish_id, condition_id, language_id)
            DO UPDATE SET
                list_low_cents = EXCLUDED.list_low_cents,
                list_avg_cents = EXCLUDED.list_avg_cents,
                sold_avg_cents = EXCLUDED.sold_avg_cents,
                n_days         = EXCLUDED.n_days,
                n_providers    = EXCLUDED.n_providers,
                updated_at     = now();

            GET DIAGNOSTICS cur_archived = ROW_COUNT;
            total_archived := total_archived + cur_archived;

            -- Delete source daily rows. Chunks are now decompressed so this
            -- runs as a plain row-level DELETE with no GUC limit.
            DELETE FROM pricing.print_price_daily
            WHERE price_date >= v_start
              AND price_date <= v_end;

            GET DIAGNOSTICS cur_deleted = ROW_COUNT;
            total_deleted := total_deleted + cur_deleted;

            RAISE NOTICE 'archive_to_weekly: batch % to %: archived=%, deleted=%',
                         v_start, v_end, cur_archived, cur_deleted;
            v_ok := TRUE;

        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'archive_to_weekly: batch % to % failed: % (SQLSTATE %)',
                          v_start, v_end, SQLERRM, SQLSTATE;
            v_ok := FALSE;
        END;

        IF v_ok THEN
            COMMIT;
            UPDATE pricing.tier_watermark
            SET    last_processed_date = v_end,
                   updated_at          = now()
            WHERE  tier_name = 'weekly';
            COMMIT;
        ELSE
            ROLLBACK;
        END IF;

        v_start := v_end + 1;
    END LOOP;

    RAISE NOTICE 'archive_to_weekly: done. total archived=%, total deleted=%',
                 total_archived, total_deleted;
END;
$$;

-- No grant changes needed — procedure signature unchanged.
