-- Migration 18: Pricing tier 2/3 — source-preserving daily/weekly rollup
--
-- Replaces the unpopulated print_price_daily stub (wrong grain, no source_id,
-- had p25/p75) and creates print_price_weekly (never applied to live DB),
-- print_price_latest (current-price snapshot), and tier_watermark (resumable
-- procedure state). Both tier 2 and tier 3 are TimescaleDB hypertables.
--
-- Safe to re-run for print_price_weekly / print_price_latest / tier_watermark
-- (CREATE IF NOT EXISTS). print_price_daily uses DROP + recreate because the
-- old stub has the wrong schema; the table was never populated.
--
-- See docs/superpowers/specs/2026-04-30-pricing-tier2-tier3-design.md

BEGIN;

-- =========================================================================
-- 1. print_price_daily (Tier 2)
--    DROP + recreate: old stub had wrong grain (no source_id, had p25/p75).
--    Table was defined in 06_prices.sql but never populated, so no data loss.
-- =========================================================================
DROP TABLE IF EXISTS pricing.print_price_daily CASCADE;

CREATE TABLE pricing.print_price_daily (
    price_date          DATE        NOT NULL,
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_daily_pk PRIMARY KEY (
        price_date, card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    ),
    CONSTRAINT chk_ppd_prices_nonneg CHECK (
        (list_low_cents  IS NULL OR list_low_cents  >= 0) AND
        (list_avg_cents  IS NULL OR list_avg_cents  >= 0) AND
        (sold_avg_cents  IS NULL OR sold_avg_cents  >= 0)
    )
    -- chk_ppd_low_le_avg intentionally omitted: MIN(list_low) vs AVG(list_avg)
    -- across providers does not guarantee low <= avg.
);

SELECT create_hypertable(
    'pricing.print_price_daily',
    by_range('price_date', INTERVAL '7 days'),
    if_not_exists => TRUE
);

ALTER TABLE pricing.print_price_daily
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
        timescaledb.compress_orderby   = 'price_date DESC'
    );

SELECT add_compression_policy(
    'pricing.print_price_daily',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- =========================================================================
-- 2. print_price_weekly (Tier 3)
--    Never applied to the live DB (schema file had a syntax error and a
--    "never applied" comment). DROP IF EXISTS + CREATE to replace any stub.
-- =========================================================================
DROP TABLE IF EXISTS pricing.print_price_weekly CASCADE;

CREATE TABLE pricing.print_price_weekly (
    price_week          DATE        NOT NULL,
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_days              SMALLINT,
    n_providers         SMALLINT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_weekly_pk PRIMARY KEY (
        price_week, card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    ),
    CONSTRAINT chk_ppw_prices_nonneg CHECK (
        (list_low_cents  IS NULL OR list_low_cents  >= 0) AND
        (list_avg_cents  IS NULL OR list_avg_cents  >= 0) AND
        (sold_avg_cents  IS NULL OR sold_avg_cents  >= 0)
    ),
    CONSTRAINT chk_ppw_n_days CHECK (n_days IS NULL OR (n_days >= 1 AND n_days <= 7))
);

COMMENT ON COLUMN pricing.print_price_weekly.price_week IS
    'Monday of the ISO week (DATE_TRUNC(''week'', price_date))';

SELECT create_hypertable(
    'pricing.print_price_weekly',
    by_range('price_week', INTERVAL '28 days'),
    if_not_exists => TRUE
);

ALTER TABLE pricing.print_price_weekly
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
        timescaledb.compress_orderby   = 'price_week DESC'
    );

SELECT add_compression_policy(
    'pricing.print_price_weekly',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- =========================================================================
-- 3. print_price_latest — current-price snapshot (plain table, not hypertable)
-- =========================================================================
CREATE TABLE IF NOT EXISTS pricing.print_price_latest (
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    price_date          DATE        NOT NULL,
    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,

    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_latest_pk PRIMARY KEY (
        card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    )
);

-- =========================================================================
-- 4. tier_watermark — one row per tier, tracks last successfully processed date
-- =========================================================================
CREATE TABLE IF NOT EXISTS pricing.tier_watermark (
    tier_name           TEXT        NOT NULL PRIMARY KEY,
    last_processed_date DATE        NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO pricing.tier_watermark (tier_name, last_processed_date) VALUES
    ('daily',  '1970-01-01'),
    ('weekly', '1970-01-01')
ON CONFLICT (tier_name) DO NOTHING;

-- =========================================================================
-- 5. Indexes
-- =========================================================================

-- print_price_daily
CREATE INDEX IF NOT EXISTS idx_ppd_card_source_date
    ON pricing.print_price_daily (card_version_id, source_id, price_date DESC);

CREATE INDEX IF NOT EXISTS idx_ppd_date_dims
    ON pricing.print_price_daily (price_date, finish_id, condition_id, language_id);

-- print_price_weekly
CREATE INDEX IF NOT EXISTS idx_ppw_card_source_week
    ON pricing.print_price_weekly (card_version_id, source_id, price_week DESC);

CREATE INDEX IF NOT EXISTS idx_ppw_week_dims
    ON pricing.print_price_weekly (price_week, finish_id, condition_id, language_id);

-- print_price_latest
CREATE INDEX IF NOT EXISTS idx_ppl_card_source
    ON pricing.print_price_latest (card_version_id, source_id);

COMMIT;

-- =========================================================================
-- 6. refresh_daily_prices — populate tier 2 + print_price_latest from tier 1
-- =========================================================================
CREATE OR REPLACE PROCEDURE pricing.refresh_daily_prices(
    p_from DATE DEFAULT NULL,
    p_to   DATE DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_from         DATE;
    v_to           DATE;
    v_start        DATE;
    v_end          DATE;
    v_batch_days   INT  := 30;
    v_ok           BOOLEAN;
    cur_rows       BIGINT;
    total_daily    BIGINT := 0;
    total_latest   BIGINT := 0;
BEGIN
    -- -----------------------------------------------------------------------
    -- Resolve date range
    -- -----------------------------------------------------------------------
    IF p_from IS NULL THEN
        SELECT last_processed_date + 1
        INTO   v_from
        FROM   pricing.tier_watermark
        WHERE  tier_name = 'daily';

        IF v_from IS NULL THEN
            RAISE EXCEPTION 'tier_watermark has no daily row; re-seed or pass p_from explicitly';
        END IF;
    ELSE
        v_from := p_from;
    END IF;

    v_to := COALESCE(p_to, CURRENT_DATE - 1);

    IF v_from > v_to THEN
        RAISE NOTICE 'refresh_daily_prices: nothing to do (from=% > to=%)', v_from, v_to;
        RETURN;
    END IF;

    RAISE NOTICE 'refresh_daily_prices: processing % to %', v_from, v_to;

    -- -----------------------------------------------------------------------
    -- Batch loop (30-day windows, same pattern as load_staging_prices_batched)
    -- -----------------------------------------------------------------------
    v_start := v_from;
    WHILE v_start <= v_to LOOP
        v_end := LEAST(v_start + (v_batch_days - 1), v_to);
        v_ok  := FALSE;

        BEGIN
            SET LOCAL work_mem                        = '512MB';
            SET LOCAL maintenance_work_mem            = '1GB';
            SET LOCAL synchronous_commit              = off;
            SET LOCAL max_parallel_workers_per_gather = 4;

            -- Build the daily aggregate from tier 1 for this batch window.
            -- JOIN path: price_observation → source_product → mtg_card_products
            DROP TABLE IF EXISTS _daily_batch;
            CREATE TEMP TABLE _daily_batch ON COMMIT DROP AS
            SELECT
                po.ts_date                                      AS price_date,
                mcp.card_version_id,
                sp.source_id,
                po.price_type_id                               AS transaction_type_id,
                po.finish_id,
                po.condition_id,
                po.language_id,
                MIN(po.list_low_cents)::INTEGER                AS list_low_cents,
                AVG(po.list_avg_cents)::INTEGER                AS list_avg_cents,
                AVG(po.sold_avg_cents)::INTEGER                AS sold_avg_cents,
                COUNT(DISTINCT po.data_provider_id)::SMALLINT  AS n_providers
            FROM  pricing.price_observation po
            JOIN  pricing.source_product    sp  ON sp.source_product_id = po.source_product_id
            JOIN  pricing.mtg_card_products mcp ON mcp.product_id       = sp.product_id
            WHERE po.ts_date >= v_start
              AND po.ts_date <= v_end
              AND NOT (po.list_low_cents IS NULL
                   AND po.list_avg_cents IS NULL
                   AND po.sold_avg_cents IS NULL)
            GROUP BY
                po.ts_date,
                mcp.card_version_id, sp.source_id,
                po.price_type_id, po.finish_id, po.condition_id, po.language_id;

            -- Upsert into print_price_daily
            INSERT INTO pricing.print_price_daily (
                price_date, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            )
            SELECT
                price_date, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            FROM _daily_batch
            ON CONFLICT (price_date, card_version_id, source_id,
                         transaction_type_id, finish_id, condition_id, language_id)
            DO UPDATE SET
                list_low_cents = EXCLUDED.list_low_cents,
                list_avg_cents = EXCLUDED.list_avg_cents,
                sold_avg_cents = EXCLUDED.sold_avg_cents,
                n_providers    = EXCLUDED.n_providers,
                updated_at     = now();

            GET DIAGNOSTICS cur_rows = ROW_COUNT;
            total_daily := total_daily + cur_rows;

            -- Upsert into print_price_latest — only advance when newer.
            -- DISTINCT ON collapses multiple dates for the same key within the
            -- batch window; ORDER BY price_date DESC keeps the most-recent row.
            INSERT INTO pricing.print_price_latest (
                card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                price_date, list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            )
            SELECT DISTINCT ON (card_version_id, source_id, transaction_type_id,
                                finish_id, condition_id, language_id)
                card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                price_date, list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            FROM _daily_batch
            ORDER BY card_version_id, source_id, transaction_type_id,
                     finish_id, condition_id, language_id,
                     price_date DESC
            ON CONFLICT (card_version_id, source_id, transaction_type_id,
                         finish_id, condition_id, language_id)
            DO UPDATE SET
                price_date     = EXCLUDED.price_date,
                list_low_cents = EXCLUDED.list_low_cents,
                list_avg_cents = EXCLUDED.list_avg_cents,
                sold_avg_cents = EXCLUDED.sold_avg_cents,
                n_providers    = EXCLUDED.n_providers,
                updated_at     = now()
            WHERE EXCLUDED.price_date >= pricing.print_price_latest.price_date;

            GET DIAGNOSTICS cur_rows = ROW_COUNT;
            total_latest := total_latest + cur_rows;

            RAISE NOTICE 'refresh_daily_prices: batch % to %: daily=%, latest_updated=%',
                         v_start, v_end, total_daily, total_latest;
            v_ok := TRUE;

        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'refresh_daily_prices: batch % to % failed: % (SQLSTATE %)',
                          v_start, v_end, SQLERRM, SQLSTATE;
            v_ok := FALSE;
        END;

        IF v_ok THEN
            COMMIT;
            -- Advance watermark per batch so a crash mid-run is resumable.
            UPDATE pricing.tier_watermark
            SET    last_processed_date = v_end,
                   updated_at          = now()
            WHERE  tier_name = 'daily';
            COMMIT;
        ELSE
            ROLLBACK;
        END IF;

        v_start := v_end + 1;
    END LOOP;

    RAISE NOTICE 'refresh_daily_prices: done. total daily=%, total latest_updated=%',
                 total_daily, total_latest;
END;
$$;

-- =========================================================================
-- 7. archive_to_weekly — roll up tier 2 rows older than N years into tier 3
-- =========================================================================
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
    v_batch_weeks   INT  := 4;
    v_ok            BOOLEAN;
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
        -- Batch = v_batch_weeks × 7 days, capped at cutoff.
        v_end := LEAST(v_start + (v_batch_weeks * 7 - 1), v_cutoff - 1);
        v_ok  := FALSE;

        BEGIN
            SET LOCAL work_mem             = '512MB';
            SET LOCAL maintenance_work_mem = '1GB';
            SET LOCAL synchronous_commit   = off;

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

            -- Upsert into print_price_weekly (idempotent re-runs are safe)
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

            -- Delete the source daily rows only after a successful upsert.
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

-- =========================================================================
-- 8. Grants
--    app_celery: full DML on tables + EXECUTE on procedures.
--    app_rw / app_admin: full DML (mirrored; apply_schema_grants.sql is
--    authoritative but explicit here for migrations run before a full refresh).
--    app_ro: SELECT only.
-- =========================================================================

-- print_price_daily
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_daily TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_daily TO app_ro;

-- print_price_weekly
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_weekly TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_weekly TO app_ro;

-- print_price_latest
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_latest TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_latest TO app_ro;

-- tier_watermark
GRANT SELECT, INSERT, UPDATE ON pricing.tier_watermark TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.tier_watermark TO app_ro;

-- Procedures
GRANT EXECUTE ON PROCEDURE pricing.refresh_daily_prices(DATE, DATE) TO app_celery, app_rw, app_admin;
GRANT EXECUTE ON PROCEDURE pricing.archive_to_weekly(INTERVAL)      TO app_celery, app_rw, app_admin;
