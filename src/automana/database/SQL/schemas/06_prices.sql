BEGIN;
CREATE SCHEMA IF NOT EXISTS pricing;
CREATE TABLE IF NOT EXISTS pricing.currency_ref (
    currency_code VARCHAR(3) PRIMARY KEY,  -- e.g., USD, EUR, JPY
    currency_name TEXT NOT NULL
);
INSERT INTO pricing.currency_ref (currency_code, currency_name) VALUES
  ('USD', 'US Dollar'),
  ('EUR', 'Euro'),
  ('JPY', 'Japanese Yen'),
  ('CAD', 'Canadian Dollar'),
  ('GBP', 'British Pound');
CREATE TABLE IF NOT EXISTS pricing.price_source ( --market marketplace or website where the price was observed, e.g., tcgplayer, cardkingdom, ebay, amazon, etc.
  source_id   SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'tcgplayer','cardkingdom','ebay','amazon', etc.
  currency_code VARCHAR(3) NOT NULL DEFAULT 'USD' REFERENCES pricing.currency_ref(currency_code),
  name       TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pricing.data_provider (
  data_provider_id SMALLSERIAL PRIMARY KEY,
  code             TEXT UNIQUE NOT NULL,   -- 'api','web_scrape','manual_entry', etc.
  description      TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO pricing.data_provider (code, description) VALUES
  ('mtgstocks', 'MTGStocks price scrape'),
  ('mtgjson',   'MTGJson bulk data file'),
  ('scryfall',  'Scryfall API')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS pricing.price_metric (
  metric_id   SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'low','avg','high','market','list','sold','median'
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pricing.transaction_type (
    transaction_type_id SERIAL PRIMARY KEY,
    transaction_type_code TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO pricing.transaction_type (transaction_type_code) VALUES 
('sell'), 
('buy')
ON CONFLICT (transaction_type_code) DO NOTHING;
CREATE TABLE IF NOT EXISTS pricing.card_condition (
  condition_id SMALLSERIAL PRIMARY KEY,
  code         TEXT UNIQUE default 'NM',  -- 'NM','LP','MP','HP','U' (unknown), 'D'
  description  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pricing.card_finished(
    finish_id   SMALLSERIAL PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,   -- 'nonfoil','foil','etched','gilded'
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Maps MTGStocks name suffixes (e.g. "Surge Foil") to their finish_id.
-- Used by load_staging_prices_batched, load_prices_from_staged_batched, and
-- resolve_price_rejects to assign granular finishes instead of generic FOIL.
CREATE TABLE IF NOT EXISTS pricing.mtgstock_name_finish_suffix (
    suffix     TEXT PRIMARY KEY,
    finish_id  SMALLINT NOT NULL REFERENCES pricing.card_finished(finish_id)
);

CREATE TABLE IF NOT EXISTS pricing.card_game (
  game_id     SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'mtg','yugioh','pokemon', etc.
  name       TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pricing.product_ref(
    product_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),  -- unique identifier for the product in the sho
    game_id SMALLINT NOT NULL REFERENCES card_catalog.card_games_ref(game_id),
     -- additional fields like name, set, etc. can be added here
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE pricing.mtg_card_products (
    product_id UUID PRIMARY KEY REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    card_version_id UUID NOT NULL REFERENCES card_catalog.card_version(card_version_id),
    game_version_id SMALLINT REFERENCES card_catalog.games_ref(game_id), --if the card is paper, mtgo, etc
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (card_version_id)
);
CREATE TABLE pricing.source_product (
    source_product_id BIGSERIAL PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    source_id SMALLINT NOT NULL REFERENCES pricing.price_source(source_id) ON DELETE CASCADE,
     -- additional fields like source_product_code, url, etc. can be added here
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (product_id, source_id)
);
------------------------------fill references table
INSERT INTO pricing.card_condition (code, description) VALUES
  ('NM', 'Near Mint'),
  ('LP', 'Lightly Played'),
  ('MP', 'Moderately Played'),
  ('HP', 'Heavily Played'),
  ('DMG','Damaged'),
  ('SP', 'Slightly Played')
ON CONFLICT (code) DO NOTHING;

-- Price metrics
INSERT INTO pricing.price_metric (code, description) VALUES
  ('price_low',    'Price low'),
  ('price_avg',    'Price average'),
  ('price_market', 'Market price')
ON CONFLICT (code) DO NOTHING;

-- Finishes
INSERT INTO pricing.card_finished (code, description) VALUES
  ('NONFOIL',      'Nonfoil'),
  ('FOIL',         'Foil'),
  ('ETCHED',       'Etched'),
  ('SURGE_FOIL',   'Surge Foil'),
  ('RIPPLE_FOIL',  'Ripple Foil'),
  ('RAINBOW_FOIL', 'Rainbow Foil')
ON CONFLICT (code) DO NOTHING;

INSERT INTO pricing.mtgstock_name_finish_suffix (suffix, finish_id) VALUES
  ('Surge Foil',    (SELECT finish_id FROM pricing.card_finished WHERE code = 'SURGE_FOIL')),
  ('Ripple Foil',   (SELECT finish_id FROM pricing.card_finished WHERE code = 'RIPPLE_FOIL')),
  ('Rainbow Foil',  (SELECT finish_id FROM pricing.card_finished WHERE code = 'RAINBOW_FOIL')),
  ('Foil Etched',   (SELECT finish_id FROM pricing.card_finished WHERE code = 'ETCHED')),
  ('Ripper Foil',   (SELECT finish_id FROM pricing.card_finished WHERE code = 'FOIL')),
  ('Textured Foil', (SELECT finish_id FROM pricing.card_finished WHERE code = 'FOIL'))
ON CONFLICT (suffix) DO NOTHING;

INSERT INTO pricing.price_source (code, name, currency_code) VALUES
  ('tcg', 'tcgplayer', 'USD'),
  ('cardkingdom', 'Card Kingdom', 'USD'),
  ('cardmarket', 'Cardmarket', 'EUR'),
  ('starcitygames', 'Star City Games', 'USD'),
  ('ebay', 'eBay', 'USD'),
  ('amazon', 'Amazon', 'USD'),
  ('mtgstocks', 'MTGStocks', 'USD')
ON CONFLICT (code) DO NOTHING;
-------------------------------------------------------------------------------price observation table and staging tables for the ETL process
-- Finish default: NONFOIL
CREATE OR REPLACE FUNCTION pricing.default_finish_id()
RETURNS SMALLINT
LANGUAGE sql
STABLE
AS $$
  SELECT finish_id
  FROM pricing.card_finished
  WHERE code = 'NONFOIL'
  LIMIT 1;
$$;

-- Condition default: NM
CREATE OR REPLACE FUNCTION pricing.default_condition_id()
RETURNS SMALLINT
LANGUAGE sql
STABLE
AS $$
  SELECT condition_id
  FROM pricing.card_condition
  WHERE code = 'NM'
  LIMIT 1;
$$;

-- Language default: en
CREATE OR REPLACE FUNCTION card_catalog.default_language_id()
RETURNS SMALLINT
LANGUAGE sql
STABLE
AS $$
  SELECT language_id
  FROM card_catalog.language_ref
  WHERE language_code = 'en'
  LIMIT 1;
$$;
------------------------------------------------------------------------------------------
--Tier 1: All prices from all sources
--take 2:
CREATE TABLE IF NOT EXISTS pricing.price_observation(
    ts_date DATE NOT NULL,
    price_type_id INTEGER NOT NULL REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id SMALLINT NOT NULL
        REFERENCES pricing.card_finished(finish_id)
        DEFAULT pricing.default_finish_id(),

    condition_id SMALLINT
        REFERENCES pricing.card_condition(condition_id)
        DEFAULT pricing.default_condition_id(),

    language_id SMALLINT
        REFERENCES card_catalog.language_ref(language_id)
        DEFAULT card_catalog.default_language_id(),

    list_low_cents INTEGER,
    list_avg_cents INTEGER,
    sold_avg_cents INTEGER,

    list_count INTEGER,
    sold_count INTEGER,

    source_product_id BIGINT NOT NULL REFERENCES pricing.source_product(source_product_id),
    data_provider_id SMALLINT NOT NULL REFERENCES pricing.data_provider(data_provider_id),

    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (ts_date, source_product_id,  price_type_id, finish_id, condition_id, language_id, data_provider_id),--changed

    CONSTRAINT chk_nonneg_prices CHECK (
    (list_low_cents IS NULL OR list_low_cents >= 0) AND
    (list_avg_cents IS NULL OR list_avg_cents >= 0) AND
    (sold_avg_cents IS NULL OR sold_avg_cents >= 0)
  )
  -- NOTE: chk_low_le_avg was removed from the live DB before data load began
  -- (the v3 rebuild of price_observation never included it). Do not add it back
  -- without verifying existing data satisfies the constraint.
);
SELECT create_hypertable('pricing.price_observation',
                         by_range('ts_date'),
                         if_not_exists => TRUE);

-- Add a space (hash) dimension on source_product_id for parallelism & chunk fan-out:
--not good for one diskSELECT add_dimension('pricing.price_observation', 'source_product_id', number_partitions => 8);

--set chunk time
-- NOTE: live DB uses 7 days (was changed from the original 30 days after initial deploy)
SELECT set_chunk_time_interval('pricing.price_observation', INTERVAL '7 days');

CREATE INDEX IF NOT EXISTS idx_price_date ON pricing.price_observation(source_product_id, ts_date DESC);


ALTER TABLE pricing.price_observation
  SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'source_product_id, price_type_id, finish_id',
       timescaledb.compress_orderby   = 'ts_date DESC');

-- Auto-compress anything older than 180 days:
SELECT add_compression_policy('pricing.price_observation', INTERVAL '180 days');
-------------------------------------------------------------------------

--Tier 2: daily -> 5 years
-- Populated by pricing.refresh_daily_prices(). TimescaleDB hypertable.
-- See migration_18_pricing_tiers.sql for the full DDL rationale.
CREATE TABLE IF NOT EXISTS pricing.print_price_daily (
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
        (list_low_cents IS NULL OR list_low_cents >= 0) AND
        (list_avg_cents IS NULL OR list_avg_cents >= 0) AND
        (sold_avg_cents IS NULL OR sold_avg_cents >= 0)
    )
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

SELECT add_compression_policy('pricing.print_price_daily', INTERVAL '30 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_ppd_card_source_date
    ON pricing.print_price_daily (card_version_id, source_id, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_ppd_date_dims
    ON pricing.print_price_daily (price_date, finish_id, condition_id, language_id);

--Tier 3: weekly aggregate for data older than 5 years
-- Populated by pricing.archive_to_weekly(). TimescaleDB hypertable.
CREATE TABLE IF NOT EXISTS pricing.print_price_weekly (
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
        (list_low_cents IS NULL OR list_low_cents >= 0) AND
        (list_avg_cents IS NULL OR list_avg_cents >= 0) AND
        (sold_avg_cents IS NULL OR sold_avg_cents >= 0)
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

SELECT add_compression_policy('pricing.print_price_weekly', INTERVAL '7 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_ppw_card_source_week
    ON pricing.print_price_weekly (card_version_id, source_id, price_week DESC);
CREATE INDEX IF NOT EXISTS idx_ppw_week_dims
    ON pricing.print_price_weekly (price_week, finish_id, condition_id, language_id);

-- print_price_latest — current-price snapshot (one row per dimension key)
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

CREATE INDEX IF NOT EXISTS idx_ppl_card_source
    ON pricing.print_price_latest (card_version_id, source_id);

-- tier_watermark — tracks last successfully processed date per tier
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
-- refresh_daily_prices — populate tier 2 + print_price_latest from tier 1
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
-- archive_to_weekly — roll up tier 2 rows older than N years into tier 3
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
    v_batch_days    INT  := 2;
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
        -- Batch = v_batch_days days, capped at cutoff.
        v_end := LEAST(v_start + (v_batch_days - 1), v_cutoff - 1);
        v_ok  := FALSE;

        BEGIN
            SET LOCAL work_mem             = '128MB';
            SET LOCAL maintenance_work_mem = '256MB';
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

-- Grants for new tier 2/3 tables and procedures
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_daily   TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_daily   TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_weekly  TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_weekly  TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_latest  TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_latest  TO app_ro;
GRANT SELECT, INSERT, UPDATE ON pricing.tier_watermark              TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.tier_watermark      TO app_ro;
GRANT EXECUTE ON PROCEDURE pricing.refresh_daily_prices(DATE, DATE) TO app_celery, app_rw, app_admin;
GRANT EXECUTE ON PROCEDURE pricing.archive_to_weekly(INTERVAL)      TO app_celery, app_rw, app_admin;

-------------------------------------------------------------------------------
--migration
-------------------------------------------------------------------------------
--from tier 1 to tier 2


--Tier 3: weekly aggre for older than 5 years
----------------------------Staging process
DROP TABLE IF EXISTS pricing.raw_mtg_stock_price;--nedd to add the ids to link to the card_version and product_ref
CREATE TABLE pricing.raw_mtg_stock_price(
    ts_date       DATE        NOT NULL,
    game_code     TEXT       NOT NULL, --REFERENCES card_game_ref(game_id),
    print_id      BIGINT      NOT NULL,
    price_low     NUMERIC(12,4),
    price_avg     NUMERIC(12,4),
    price_foil   NUMERIC(12,4),
    price_market NUMERIC(12,4),
    price_market_foil NUMERIC(12,4),
    source_code     TEXT    NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    card_name TEXT,
    set_abbr TEXT,
    collector_number TEXT,
    scryfall_id TEXT,
    tcg_id TEXT,
    cardtrader_id TEXT
);
COMMENT ON TABLE pricing.raw_mtg_stock_price IS 'Raw price data ingested from MTG Stocks, with one row per print_id and date, and multiple price metrics as columns. This is the landing table before transformation and loading into the dimensional model.';
CREATE INDEX idx_raw_price_date ON pricing.raw_mtg_stock_price(print_id, ts_date);
DROP TABLE IF EXISTS pricing.stg_price_observation;
-- Wide model: one row per (ts_date, source_product_id, is_foil, source_code, data_provider_id)
-- carrying three metric columns (list_low_cents, list_avg_cents, sold_avg_cents) plus a raw
-- `value` in source currency units (NUMERIC). product_id/card_version_id/source_product_id
-- are expected to be already resolved by load_staging_prices_batched before insertion.
CREATE UNLOGGED TABLE pricing.stg_price_observation (
    stg_id            BIGSERIAL      PRIMARY KEY,
    ts_date           DATE           NOT NULL,
    game_code         TEXT           NOT NULL,
    print_id          BIGINT         NOT NULL,
    list_low_cents    INTEGER,
    list_avg_cents    INTEGER,
    sold_avg_cents    INTEGER,
    is_foil           BOOLEAN        NOT NULL,
    source_code       TEXT           NOT NULL,
    data_provider_id  SMALLINT       NOT NULL,
    value             NUMERIC(12,4),
    product_id        UUID           NOT NULL,
    card_version_id   UUID,
    source_product_id BIGINT         NOT NULL,
    set_abbr          TEXT,
    collector_number  TEXT,
    card_name         TEXT,
    scryfall_id       TEXT,
    tcg_id            TEXT,
    scraped_at        TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- Reject table for staging-resolution failures. Pre-created here so the
-- load_staging_prices_batched procedure (called by app_celery, which has no
-- CREATE on pricing per the grants design) does not need to create it at
-- runtime. The procedure still has CREATE TABLE IF NOT EXISTS — that is now
-- a no-op on each call.
DROP TABLE IF EXISTS pricing.stg_price_observation_reject;
CREATE TABLE pricing.stg_price_observation_reject (
    ts_date date NOT NULL,
    game_code text NOT NULL,
    print_id bigint NOT NULL,
    source_code text NOT NULL,
    data_provider_id SMALLINT NOT NULL,
    scraped_at timestamptz NOT NULL,
    list_low_cents INTEGER,
    list_avg_cents INTEGER,
    sold_avg_cents INTEGER,
    is_foil boolean NOT NULL,
    value numeric(12,4),
    card_name text,
    set_abbr text,
    collector_number text,
    scryfall_id text,
    tcg_id text,
    cardtrader_id text,
    is_terminal boolean NOT NULL DEFAULT false,
    terminal_reason text,
    resolution_attempted_at timestamptz NOT NULL DEFAULT now(),
    reject_reason text NOT NULL,
    resolved_at timestamptz,
    resolved_source_product_id bigint,
    resolved_product_id uuid,
    resolved_card_version_id uuid,
    resolved_method text
);

-- Index used by load_staging_prices_batched after batch inserts. Pre-created
-- here for the same reason as the reject table above.
CREATE INDEX IF NOT EXISTS stg_price_obs_date_spid_foil_idx
ON pricing.stg_price_observation (ts_date, source_product_id, is_foil);
---------------------------------------------------------------------------------------------new

  CREATE INDEX IF NOT EXISTS raw_mtg_stock_price_ts_date_idx
  ON pricing.raw_mtg_stock_price (ts_date);

  -- identifier lookup accelerators
  CREATE INDEX IF NOT EXISTS card_identifier_ref_name_idx
  ON card_catalog.card_identifier_ref (identifier_name, card_identifier_ref_id);

  -- card_external_identifier (ref_id, value) index lives in 02_card_schema.sql
  -- next to the table definition (idx_card_external_identifier_ref_value).

  -- fallback
  CREATE INDEX IF NOT EXISTS sets_set_code_idx
  ON card_catalog.sets (set_code);

  CREATE INDEX IF NOT EXISTS card_version_set_coll_idx
  ON card_catalog.card_version (set_id, collector_number);

  -- product lookup
  CREATE INDEX IF NOT EXISTS mtg_card_products_cvid_idx
  ON pricing.mtg_card_products (card_version_id);

  CREATE INDEX IF NOT EXISTS source_product_prod_source_idx
  ON pricing.source_product (product_id, source_id);
  
------------------------------------------------------------------
--Step 1: Load raw data into staging with resolution of product_source_id, and capture rejects for later inspection
-- WARNING: The INSERT INTO stg_price_observation block below references the OLD column model
-- (list_low_cents, list_avg_cents, sold_avg_cents, data_provider_id). These columns no longer
-- exist in the live stg_price_observation table. The live DB procedure body has been updated
-- separately. If re-applying this file, update the INSERT block to use the metric_code/value model.
------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched(source_name VARCHAR(20), batch_days int DEFAULT 30, p_ingestion_run_id INT DEFAULT NULL)
LANGUAGE plpgsql
AS $$
DECLARE
  v_min date;
  v_max date;
  v_start date;
  v_end   date;
  v_source_id SMALLINT;
  v_ok boolean;
  v_mtg_game_id SMALLINT;
  v_data_provider_id SMALLINT;
  cur_rows bigint;
  total_inserted bigint := 0;
  v_batch_seq   INT := 0;
  v_batch_start TIMESTAMPTZ;
  v_total_days  INT;
  -- Promotion dimension IDs — resolved once before the loop
  v_price_type_id      int;
  v_finish_foil_id     smallint;
  v_finish_default_id  smallint;
  v_condition_id       smallint;
  v_language_id        smallint;
  -- Per-batch promotion counters
  v_prom_rows          bigint;
  v_prom_deleted       bigint;
  total_promoted       bigint := 0;
  total_staged_drained bigint := 0;

BEGIN
  -- determine overall date range from raw data
  SET LOCAL work_mem = '512MB';
  SET LOCAL maintenance_work_mem = '1GB';
  -- NOTE: temp_buffers cannot be changed after first temp-table access in a
  -- session, so it is NOT set here.  The target value (256 MB = 32768 pages)
  -- is pre-configured at pool-connection time via asyncpg server_settings in
  -- core/database.py, which makes this SET LOCAL a no-op on pool-recycled
  -- connections and avoids InvalidParameterValueError on second+ invocations.
  SET LOCAL synchronous_commit = off;
  SET LOCAL max_parallel_workers_per_gather = 4;

  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM pricing.raw_mtg_stock_price;
  IF v_min IS NULL THEN
    RAISE NOTICE 'load_staging_prices_batched: no rows in raw_mtg_stock_price';
    RETURN;
  END IF;
  v_total_days := (v_max - v_min) + 1;

  --will need to add the foil code translation in the same way as the metric code and source code translation
  SELECT ps.source_id INTO v_source_id
  FROM pricing.price_source ps
  WHERE ps.code = source_name;

  IF v_source_id IS NULL THEN
    RAISE EXCEPTION 'Missing source_code=% in pricing.price_source', source_name;
  END IF;

  SELECT dp.data_provider_id INTO v_data_provider_id
  FROM pricing.data_provider dp
  WHERE dp.code = 'mtgstocks';

  IF v_data_provider_id IS NULL THEN
    RAISE EXCEPTION 'Missing pricing.data_provider row with code=mtgstocks';
  END IF;
-----------------------------------------------
  SELECT cg.game_id INTO v_mtg_game_id
  FROM card_catalog.card_games_ref cg
  WHERE lower(cg.code) IN ('mtg', 'magic', 'magic_the_gathering')
  ORDER BY CASE lower(cg.code) WHEN 'mtg' THEN 1 ELSE 2 END
  LIMIT 1;

  -- stg_price_observation_reject is pre-created by 06_prices.sql schema section;
  -- app_celery only has USAGE on the pricing schema (not CREATE), so the
  -- CREATE TABLE IF NOT EXISTS that used to live here was removed.

  v_start := v_min;

  -- Resolve promotion dimension IDs once — stable across all batches.
  v_finish_default_id := pricing.default_finish_id();
  SELECT cf.finish_id INTO v_finish_foil_id
  FROM pricing.card_finished cf
  WHERE lower(cf.code) IN ('foil', 'foiled', 'premium')
  ORDER BY cf.finish_id LIMIT 1;
  IF v_finish_foil_id IS NULL THEN
    v_finish_foil_id := v_finish_default_id;
  END IF;
  SELECT tt.transaction_type_id INTO v_price_type_id
  FROM pricing.transaction_type tt
  WHERE lower(tt.transaction_type_code) = 'sell'
  ORDER BY tt.transaction_type_id LIMIT 1;
  IF v_price_type_id IS NULL THEN
    RAISE EXCEPTION 'No ''sell'' row in pricing.transaction_type';
  END IF;
  v_condition_id := pricing.default_condition_id();
  v_language_id  := card_catalog.default_language_id();

  WHILE v_start <= v_max LOOP
    v_batch_seq   := v_batch_seq + 1;
    v_batch_start := clock_timestamp();
    v_end := LEAST(v_start + (batch_days - 1), v_max);
    v_ok :=false;
    BEGIN
      -- Session locals are cleared by the previous COMMIT, so re-apply.
      SET LOCAL work_mem                    = '512MB';
      SET LOCAL maintenance_work_mem        = '1GB';
      SET LOCAL synchronous_commit          = off;
      SET LOCAL max_parallel_workers_per_gather = 4;

      RAISE NOTICE 'Loading raw -> staging for % to %', v_start, v_end;
      
      -- -------------------------------------------------------------------------
      -- 1) Temp raw slice for this batch
      -- -------------------------------------------------------------------------
      DROP TABLE IF EXISTS tmp_raw_batch;
          CREATE TEMP TABLE tmp_raw_batch ON COMMIT DROP AS
      SELECT
        s.ts_date,
        s.game_code,
        s.print_id,
        s.price_low,
        s.price_avg,
        s.price_foil,
        s.price_market,
        s.price_market_foil,
        s.source_code,
        s.scraped_at,
        s.card_name,
        s.set_abbr,
        s.collector_number,
        s.scryfall_id,
        s.tcg_id,
        s.cardtrader_id,
        v_data_provider_id AS data_provider_id
      FROM pricing.raw_mtg_stock_price s
      WHERE s.ts_date >= v_start
        AND s.ts_date <= v_end;

      DROP TABLE IF EXISTS tmp_batch_foil_split;
      CREATE TEMP TABLE tmp_batch_foil_split ON COMMIT DROP AS
      SELECT
        r.ts_date,
        r.game_code,
        r.print_id,
        r.source_code,
        r.scraped_at,
        r.card_name,
        r.set_abbr,
        r.collector_number,
        r.scryfall_id,
        r.tcg_id,
        r.cardtrader_id,
        (v.list_low_cents * 100)::int AS list_low_cents,
        (v.list_avg_cents * 100)::int AS list_avg_cents,
        (v.sold_avg_cents * 100)::int AS sold_avg_cents,
        v.is_foil,
        v.value,
        r.data_provider_id
      FROM tmp_raw_batch r
      CROSS JOIN LATERAL (VALUES
        -- Non-foil row: all three non-foil price fields; filter on any non-null price.
        (r.price_low, r.price_avg, r.price_market, false,
         COALESCE(r.price_avg, r.price_market, r.price_low)),
        -- Foil row: foil-specific prices only; filter on any non-null foil price.
        (NULL::numeric, r.price_foil, r.price_market_foil, true,
         COALESCE(r.price_foil, r.price_market_foil))
      ) AS v(list_low_cents, list_avg_cents, sold_avg_cents, is_foil, value)
      WHERE v.value IS NOT NULL;

      -- -------------------------------------------------------------------------
      -- 3) Resolve card_version_id with priority:
      --    (1) print map -> (2) external ids -> (3) set+collector (+name)
      -- -------------------------------------------------------------------------
      DROP TABLE IF EXISTS tmp_map_print;
  CREATE TEMP TABLE tmp_map_print ON COMMIT DROP AS
  SELECT DISTINCT
    u.print_id,
    cei.card_version_id
  FROM tmp_batch_foil_split u
  JOIN card_catalog.card_identifier_ref cir
    ON cir.identifier_name = 'mtgstock_id'
  JOIN card_catalog.card_external_identifier cei
    ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
  AND cei.value = u.print_id::text
  WHERE u.print_id IS NOT NULL;

  -- (2) external ids mapping (prefer scryfall > tcgplayer > cardtrader), keyed by print_id
  DROP TABLE IF EXISTS tmp_map_external;
  CREATE TEMP TABLE tmp_map_external ON COMMIT DROP AS
  WITH candidates AS (
    SELECT u.print_id
      , 'scryfall_id'::text   AS identifier_name
      , COALESCE(m.new_scryfall_id::text, u.scryfall_id) AS identifier_value, 1 AS prio
    FROM tmp_raw_batch u
    LEFT JOIN card_catalog.scryfall_migration m
      ON NULLIF(u.scryfall_id,'')::uuid = m.old_scryfall_id
    AND m.migration_strategy IN ('merge','move')
    AND m.new_scryfall_id IS NOT NULL
    WHERE u.scryfall_id IS NOT NULL AND u.scryfall_id <> ''

    UNION ALL
    SELECT u.print_id, 'tcgplayer_id'::text  AS identifier_name, u.tcg_id        AS identifier_value, 2 AS prio
    FROM tmp_raw_batch u WHERE u.tcg_id IS NOT NULL

    UNION ALL
    SELECT u.print_id, 'cardtrader_id'::text AS identifier_name, u.cardtrader_id AS identifier_value, 3 AS prio
    FROM tmp_raw_batch u WHERE u.cardtrader_id IS NOT NULL
  ),
  joined AS (
    SELECT c.print_id, c.prio, cei.card_version_id
    FROM candidates c
    JOIN card_catalog.card_identifier_ref cir
      ON cir.identifier_name = c.identifier_name
    JOIN card_catalog.card_external_identifier cei
      ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
    AND cei.value = c.identifier_value
  ),
  ranked AS (
    SELECT *, row_number() OVER (PARTITION BY print_id ORDER BY prio) rn
    FROM joined
  )
  SELECT print_id, card_version_id
  FROM ranked
  WHERE rn = 1;

  -- (3) fallback by set + collector (+ optional name match)
  DROP TABLE IF EXISTS tmp_map_fallback;
  CREATE TEMP TABLE tmp_map_fallback ON COMMIT DROP AS
  SELECT DISTINCT
    u.set_abbr,
    u.collector_number,
    cv.card_version_id
  FROM tmp_raw_batch u
  JOIN card_catalog.sets sr
    ON LOWER(sr.set_code) = LOWER(u.set_abbr)
  JOIN card_catalog.card_version cv
    ON cv.set_id = sr.set_id
  AND cv.collector_number::text = u.collector_number
  LEFT JOIN card_catalog.unique_cards_ref uc
    ON uc.unique_card_id = cv.unique_card_id
  WHERE u.set_abbr IS NOT NULL
    AND u.collector_number IS NOT NULL
    AND (
        u.card_name IS NULL
        OR uc.card_name IS NULL
        OR lower(uc.card_name) = lower(u.card_name)
        OR lower(u.card_name) LIKE (lower(uc.card_name) || ' (%')
    );

  -- 3d) Final resolved rows — built from tmp_batch_foil_split so that each row
  --     already carries the foil-split price columns (list_low_cents, list_avg_cents,
  --     sold_avg_cents, is_foil, value) needed by the reject insert and the staging
  --     insert downstream. tmp_map_print / tmp_map_external / tmp_map_fallback are
  --     keyed by print_id / set_abbr+collector_number, which are present on both
  --     the raw and foil-split tables.
  DROP TABLE IF EXISTS tmp_resolved;
  CREATE TEMP TABLE tmp_resolved ON COMMIT DROP AS
  SELECT
    u.*,
    COALESCE(mp.card_version_id, me.card_version_id, mf.card_version_id) AS card_version_id,
    CASE
      WHEN mp.card_version_id IS NOT NULL THEN 'PRINT_ID'
      WHEN me.card_version_id IS NOT NULL THEN 'EXTERNAL_ID'
      WHEN mf.card_version_id IS NOT NULL THEN 'SET_COLLECTOR'
      ELSE 'UNRESOLVED'
    END AS resolution_method
  FROM tmp_batch_foil_split u
  LEFT JOIN tmp_map_print mp
    ON mp.print_id = u.print_id
  LEFT JOIN tmp_map_external me
    ON me.print_id = u.print_id
  LEFT JOIN tmp_map_fallback mf
    ON mf.set_abbr = u.set_abbr
  AND mf.collector_number = u.collector_number;

  -- -------------------------------------------------------------------------
  -- 3e) Backfill mtgstock_id mapping into identifier tables (if missing)
  --     Only when we have a resolved card_version_id and a print_id.
  --     Also avoids ambiguous print_id -> multiple card_version_id in this batch.
  -- -------------------------------------------------------------------------
  WITH resolved_prints AS (
    SELECT DISTINCT
      r.print_id,
      r.card_version_id
    FROM tmp_resolved r
    WHERE r.print_id IS NOT NULL
      AND r.card_version_id IS NOT NULL
  ),
  unambiguous_print AS (
    SELECT rp.print_id, rp.card_version_id
    FROM resolved_prints rp
    JOIN (
      SELECT print_id
      FROM resolved_prints
      GROUP BY print_id
      HAVING count(DISTINCT card_version_id) = 1
    ) ok USING (print_id)
  ),
  -- choose at most one print_id per card_version_id to avoid PK conflicts
  pick_one_per_cv AS (
    SELECT DISTINCT ON (card_version_id)
      card_version_id,
      print_id::text AS print_value
    FROM unambiguous_print
    ORDER BY card_version_id, print_id
  ),
  mtgstock_ref AS (
    SELECT card_identifier_ref_id
    FROM card_catalog.card_identifier_ref
    WHERE identifier_name = 'mtgstock_id'
    LIMIT 1
  )
  -- Explicit PK conflict target — a concurrent re-run that inserted the same
  -- (card_version_id, ref_id) between the LEFT JOIN check and the INSERT
  -- gets absorbed silently. The (ref_id, value) UNIQUE constraint no longer
  -- exists (per 02_card_schema.sql comments), so this clause covers only
  -- the PK case — which is exactly what we want here.
  INSERT INTO card_catalog.card_external_identifier (card_identifier_ref_id, card_version_id, value)
  SELECT
    r.card_identifier_ref_id,
    p.card_version_id,
    p.print_value
  FROM pick_one_per_cv p
  CROSS JOIN mtgstock_ref r
  LEFT JOIN card_catalog.card_external_identifier existing_pk
    ON existing_pk.card_version_id = p.card_version_id
  AND existing_pk.card_identifier_ref_id = r.card_identifier_ref_id
  WHERE existing_pk.card_version_id IS NULL
  ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING;

      -- -------------------------------------------------------------------------
      -- 4) Send unresolved rows to reject table (so you can inspect/repair mappings)
      -- -------------------------------------------------------------------------
      INSERT INTO pricing.stg_price_observation_reject (
        ts_date, game_code, print_id, source_code, data_provider_id,scraped_at,
        list_low_cents, list_avg_cents, sold_avg_cents, is_foil, value,
        card_name, set_abbr, collector_number, scryfall_id, tcg_id, cardtrader_id,
        reject_reason
      )
      SELECT
        r.ts_date, r.game_code, r.print_id, r.source_code, r.data_provider_id, r.scraped_at,
        r.list_low_cents, r.list_avg_cents, r.sold_avg_cents, r.is_foil, r.value,
        r.card_name, r.set_abbr, r.collector_number, r.scryfall_id, r.tcg_id, r.cardtrader_id,
        'Could not resolve card_version_id via print_id/external_id/set+collector'
      FROM tmp_resolved r
      WHERE r.card_version_id IS NULL;

      -- -------------------------------------------------------------------------
      -- 5) Ensure mtg_products exist for resolved card_version_id
      -- -------------------------------------------------------------------------
      WITH need AS (
    SELECT DISTINCT r.card_version_id
    FROM tmp_resolved r
    LEFT JOIN pricing.mtg_card_products mcp
      ON mcp.card_version_id = r.card_version_id
    WHERE r.card_version_id IS NOT NULL
      AND mcp.product_id IS NULL
  ),
  gen AS (
    SELECT card_version_id, uuid_generate_v4() AS product_id
    FROM need
  ),
  ins_prod AS (
    INSERT INTO pricing.product_ref (product_id, game_id)
    SELECT product_id, v_mtg_game_id
    FROM gen
    ON CONFLICT (product_id) DO NOTHING
  )
    INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
    SELECT product_id, card_version_id
    FROM gen
    ON CONFLICT (card_version_id) DO NOTHING;
      -- -------------------------------------------------------------------------
      -- 7) Build lookup: card_version_id -> product_id -> source_product_id
      -- -------------------------------------------------------------------------
      DROP TABLE IF EXISTS tmp_product_lookup;
      CREATE TEMP TABLE tmp_product_lookup ON COMMIT DROP AS
      SELECT mcp.card_version_id, mcp.product_id
      FROM pricing.mtg_card_products mcp
      WHERE mcp.card_version_id IN (SELECT DISTINCT card_version_id FROM tmp_resolved WHERE card_version_id IS NOT NULL);

      INSERT INTO pricing.source_product (product_id, source_id)
      SELECT DISTINCT pl.product_id, v_source_id
      FROM tmp_product_lookup pl
      LEFT JOIN pricing.source_product sp
        ON sp.product_id = pl.product_id
      AND sp.source_id = v_source_id
      WHERE sp.source_product_id IS NULL
      ON CONFLICT (product_id, source_id) DO NOTHING;

      DROP TABLE IF EXISTS tmp_sp_lookup;
      CREATE TEMP TABLE tmp_sp_lookup ON COMMIT DROP AS
      SELECT
        pl.card_version_id,
        pl.product_id,
        sp.source_product_id
      FROM tmp_product_lookup pl
      JOIN pricing.source_product sp
        ON sp.product_id = pl.product_id
      AND sp.source_id = v_source_id;
      -- -------------------------------------------------------------------------
      -- 8) Insert resolved rows into staging
      -- -------------------------------------------------------------------------
      INSERT INTO pricing.stg_price_observation ( --addinf ts date
        ts_date, game_code, print_id, list_low_cents, list_avg_cents, sold_avg_cents, is_foil, source_code, data_provider_id,  value,
        product_id, card_version_id, source_product_id,
        set_abbr, collector_number, card_name, scryfall_id, tcg_id,
        scraped_at
      )
      SELECT
        r.ts_date,
          r.game_code,
          r.print_id,
          r.list_low_cents,
          r.list_avg_cents,
          r.sold_avg_cents,
          r.is_foil,
          r.source_code,
          r.data_provider_id,
          r.value,
          l.product_id,
          r.card_version_id,
          l.source_product_id,
          r.set_abbr,
          r.collector_number,
          r.card_name,
          r.scryfall_id,
          r.tcg_id,
          r.scraped_at
      FROM tmp_resolved r
      JOIN tmp_sp_lookup l
        ON l.card_version_id = r.card_version_id
      WHERE r.card_version_id IS NOT NULL;

      GET DIAGNOSTICS cur_rows = ROW_COUNT;
      total_inserted := total_inserted + cur_rows;

      -- -----------------------------------------------------------------------
      -- Inline promotion: drain staging rows for this date window immediately.
      -- Keeps stg_price_observation from accumulating across the full run.
      -- Uses distinct temp-table names (_prom_batch/_prom_dedup) to avoid
      -- colliding with the _batch/_dedup names in load_prices_from_staged_batched.
      -- -----------------------------------------------------------------------
      DROP TABLE IF EXISTS _prom_batch;
      CREATE TEMP TABLE _prom_batch ON COMMIT DROP AS
      SELECT
        s.stg_id,
        s.ts_date,
        s.source_product_id,
        s.data_provider_id,
        v_price_type_id::int                              AS price_type_id,
        COALESCE(
            fsm.finish_id,
            CASE WHEN s.is_foil THEN v_finish_foil_id
                 ELSE v_finish_default_id END
        )                                                 AS finish_id,
        v_condition_id                                    AS condition_id,
        v_language_id                                     AS language_id,
        s.list_low_cents,
        s.list_avg_cents,
        s.sold_avg_cents,
        s.scraped_at
      FROM pricing.stg_price_observation s
      LEFT JOIN pricing.mtgstock_name_finish_suffix fsm
          ON s.card_name ~ '\([^)]+\)$'
         AND fsm.suffix = regexp_replace(s.card_name, '^.+\s+\(([^)]+)\)$', '\1')
      WHERE s.ts_date >= v_start
        AND s.ts_date <= v_end
        AND NOT (s.list_low_cents IS NULL
             AND s.list_avg_cents IS NULL
             AND s.sold_avg_cents IS NULL);

      DROP TABLE IF EXISTS _prom_dedup;
      CREATE TEMP TABLE _prom_dedup ON COMMIT DROP AS
      SELECT *
      FROM (
        SELECT b.*,
               row_number() OVER (
                 PARTITION BY
                   b.ts_date,
                   b.source_product_id,
                   b.price_type_id,
                   b.finish_id,
                   b.condition_id,
                   b.language_id,
                   b.data_provider_id
                 ORDER BY b.scraped_at DESC, b.stg_id DESC
               ) AS rn
        FROM _prom_batch b
      ) x
      WHERE rn = 1;

      INSERT INTO pricing.price_observation (
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents,
        scraped_at
      )
      SELECT
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents,
        scraped_at
      FROM _prom_dedup
      ORDER BY ts_date
      ON CONFLICT (ts_date, source_product_id, price_type_id,
                   finish_id, condition_id, language_id, data_provider_id)
      DO UPDATE SET
        list_low_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_low_cents IS NOT NULL
            THEN EXCLUDED.list_low_cents
          ELSE pricing.price_observation.list_low_cents
        END,
        list_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_avg_cents IS NOT NULL
            THEN EXCLUDED.list_avg_cents
          ELSE pricing.price_observation.list_avg_cents
        END,
        sold_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.sold_avg_cents IS NOT NULL
            THEN EXCLUDED.sold_avg_cents
          ELSE pricing.price_observation.sold_avg_cents
        END,
        scraped_at = GREATEST(pricing.price_observation.scraped_at, EXCLUDED.scraped_at),
        updated_at = now();

      GET DIAGNOSTICS v_prom_rows = ROW_COUNT;
      total_promoted := total_promoted + v_prom_rows;

      DELETE FROM pricing.stg_price_observation s
      USING _prom_batch b
      WHERE s.stg_id = b.stg_id;

      GET DIAGNOSTICS v_prom_deleted = ROW_COUNT;
      total_staged_drained := total_staged_drained + v_prom_deleted;

      RAISE NOTICE 'Batch % to %: staged %, promoted %, drained %',
                   v_start, v_end, cur_rows, v_prom_rows, v_prom_deleted;
      v_ok := true;
    EXCEPTION WHEN OTHERS THEN
      RAISE WARNING 'Error processing batch % to %: %', v_start, v_end, SQLERRM;
      v_ok := false;
    -- advance to next batch
    END;
  
    if v_ok THEN
      COMMIT;
    ELSE
      ROLLBACK;
    END IF;
    IF p_ingestion_run_id IS NOT NULL THEN
      INSERT INTO ops.ingestion_step_batches (
        ingestion_run_step_id, batch_seq, range_start, range_end,
        status, items_ok, items_failed, duration_ms, error_details
      )
      SELECT
        st.id,
        v_batch_seq,
        EXTRACT(EPOCH FROM v_start)::bigint,
        EXTRACT(EPOCH FROM v_end)::bigint,
        CASE WHEN v_ok THEN 'success' ELSE 'failed' END,
        CASE WHEN v_ok THEN cur_rows ELSE 0 END,
        0,
        ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_batch_start)) * 1000)::int,
        jsonb_build_object('date_start', v_start::text, 'date_end', v_end::text,
                           'total_inserted', total_inserted,
                           'promoted', v_prom_rows)
      FROM ops.ingestion_run_steps st
      WHERE st.ingestion_run_id = p_ingestion_run_id
        AND st.step_name = 'raw_to_staging'
      LIMIT 1
      ON CONFLICT (ingestion_run_step_id, batch_seq) DO NOTHING;
      UPDATE ops.ingestion_run_steps
      SET progress = ROUND(100.0 * (v_end - v_min + 1) / NULLIF(v_total_days, 0), 2)
      WHERE ingestion_run_id = p_ingestion_run_id AND step_name = 'raw_to_staging';
      COMMIT;
    END IF;
      v_start := v_end + 1;
  END LOOP;
  -- stg_price_obs_date_spid_foil_idx is pre-created by 06_prices.sql schema section;
  -- CREATE INDEX IF NOT EXISTS removed — same reason as CREATE TABLE above.
  RAISE NOTICE 'load_staging_prices_batched: total staged %, promoted %, drained %',
               total_inserted, total_promoted, total_staged_drained;
END;
$$;

------------------------------------------------------------------
--Step 2: Move from staging to dimensional model (price_observation), with any necessary transformations
------------------------------------------------------------------


ANALYZE pricing.stg_price_observation;
CREATE OR REPLACE PROCEDURE pricing.load_prices_from_staged_batched(batch_days int DEFAULT 30)
LANGUAGE plpgsql
AS $$
DECLARE
  v_min date;
  v_max date;
  v_start date;
  v_end date;
  v_price_type_id      int;
  v_finish_foil_id     smallint;
  v_finish_default_id  smallint;
  v_condition_id       smallint;
  v_language_id        smallint;
  v_ok boolean;
  cur_rows      bigint;
  deleted_rows  bigint;
  inserted_rows bigint := 0;
  total_deleted bigint := 0;
BEGIN
  -- ------------------------------------------------------------------
  -- Pre-flight: resolve dimension ids once (cheap, stable across batches)
  -- ------------------------------------------------------------------
  v_finish_default_id := pricing.default_finish_id();

  SELECT cf.finish_id
  INTO   v_finish_foil_id
  FROM   pricing.card_finished cf
  WHERE  lower(cf.code) IN ('foil', 'foiled', 'premium')
  ORDER  BY cf.finish_id
  LIMIT  1;

  IF v_finish_foil_id IS NULL THEN
    -- No FOIL row yet; degrade to default so foil rows still load.
    v_finish_foil_id := v_finish_default_id;
  END IF;

  SELECT tt.transaction_type_id
  INTO   v_price_type_id
  FROM   pricing.transaction_type tt
  WHERE  lower(tt.transaction_type_code) = 'sell'
  ORDER  BY tt.transaction_type_id
  LIMIT  1;

  IF v_price_type_id IS NULL THEN
    RAISE EXCEPTION 'No ''sell'' row in pricing.transaction_type; cannot load price_observation';
  END IF;

  v_condition_id := pricing.default_condition_id();
  v_language_id  := card_catalog.default_language_id();

  SELECT min(ts_date), max(ts_date)
  INTO   v_min, v_max
  FROM   pricing.stg_price_observation;

  IF v_min IS NULL THEN
    RAISE NOTICE 'load_prices_from_staged_batched: staging is empty, nothing to do';
    RETURN;
  END IF;

  RAISE NOTICE 'Loading price_observation from staging for % to %', v_min, v_max;

  -- ------------------------------------------------------------------
  -- Batch loop: per-batch BEGIN/EXCEPTION/COMMIT so one bad day does
  -- not poison the whole run.
  -- ------------------------------------------------------------------
  v_start := v_min;
  WHILE v_start <= v_max LOOP
    v_end := LEAST(v_start + (batch_days - 1), v_max);
    v_ok  := false;

    BEGIN
      -- Session locals are cleared by the previous COMMIT, so re-apply.
      SET LOCAL work_mem          = '512MB';
      SET LOCAL maintenance_work_mem = '1GB';
      SET LOCAL synchronous_commit   = off;

      RAISE NOTICE 'Batch % to %', v_start, v_end;

      -- ------------------------------------------------------------------
      -- Step A: build batch slice. One staging row -> one fact row (wide).
      --   - Map is_foil -> finish_id via CASE on pre-resolved smallints.
      --   - Skip rows where all three cents columns are NULL (nothing to
      --     observe); they stay in staging and should be cleaned by the
      --     upstream loader.
      --   - Carry stg_id as surrogate for the later DELETE.
      -- ------------------------------------------------------------------
      DROP TABLE IF EXISTS _batch;
      CREATE TEMP TABLE _batch ON COMMIT DROP AS
      SELECT
        s.stg_id,
        s.ts_date,
        s.source_product_id,
        s.data_provider_id,
        v_price_type_id::int                          AS price_type_id,
        COALESCE(
            fsm.finish_id,
            CASE WHEN s.is_foil THEN v_finish_foil_id
                 ELSE v_finish_default_id END
        )                                             AS finish_id,
        v_condition_id                                AS condition_id,
        v_language_id                                 AS language_id,
        s.list_low_cents,
        s.list_avg_cents,
        s.sold_avg_cents,
        s.scraped_at
      FROM pricing.stg_price_observation s
      LEFT JOIN pricing.mtgstock_name_finish_suffix fsm
          ON s.card_name ~ '\([^)]+\)$'
         AND fsm.suffix = regexp_replace(s.card_name, '^.+\s+\(([^)]+)\)$', '\1')
      WHERE s.ts_date >= v_start
        AND s.ts_date <= v_end
        AND NOT (s.list_low_cents IS NULL
             AND s.list_avg_cents IS NULL
             AND s.sold_avg_cents IS NULL);

      -- ------------------------------------------------------------------
      -- Step B: dedup on the full fact-table PK, keep freshest scraped_at.
      --   Secondary ORDER BY stg_id DESC makes ties deterministic.
      -- ------------------------------------------------------------------
      DROP TABLE IF EXISTS _dedup;
      CREATE TEMP TABLE _dedup ON COMMIT DROP AS
      SELECT *
      FROM (
        SELECT b.*,
               row_number() OVER (
                 PARTITION BY
                   b.ts_date,
                   b.source_product_id,
                   b.price_type_id,
                   b.finish_id,
                   b.condition_id,
                   b.language_id,
                   b.data_provider_id
                 ORDER BY b.scraped_at DESC, b.stg_id DESC
               ) AS rn
        FROM _batch b
      ) x
      WHERE rn = 1;

      -- ------------------------------------------------------------------
      -- Step C: upsert into the fact table.
      --   DO UPDATE: per-column "newest non-null wins" — a newer scrape
      --   with a NULL in one column does NOT wipe a valid older value.
      --   list_count / sold_count are not populated by staging; protect
      --   any value that may have been inserted from a different source.
      -- ------------------------------------------------------------------
      INSERT INTO pricing.price_observation (
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents,
        scraped_at
      )
      SELECT
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents,
        scraped_at
      FROM _dedup
      ORDER BY ts_date
      ON CONFLICT (ts_date, source_product_id, price_type_id,
                   finish_id, condition_id, language_id, data_provider_id)
      DO UPDATE SET
        list_low_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_low_cents IS NOT NULL
            THEN EXCLUDED.list_low_cents
          ELSE pricing.price_observation.list_low_cents
        END,
        list_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_avg_cents IS NOT NULL
            THEN EXCLUDED.list_avg_cents
          ELSE pricing.price_observation.list_avg_cents
        END,
        sold_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.sold_avg_cents IS NOT NULL
            THEN EXCLUDED.sold_avg_cents
          ELSE pricing.price_observation.sold_avg_cents
        END,
        scraped_at = GREATEST(pricing.price_observation.scraped_at, EXCLUDED.scraped_at),
        updated_at = now();

      GET DIAGNOSTICS cur_rows = ROW_COUNT;
      inserted_rows := inserted_rows + cur_rows;

      -- ------------------------------------------------------------------
      -- Step D: drain consumed staging rows by surrogate key.
      --   stg_id is the PK of stg_price_observation, so this is an exact
      --   1-to-1 match on what entered _batch this iteration.
      -- ------------------------------------------------------------------
      DELETE FROM pricing.stg_price_observation s
      USING _batch b
      WHERE s.stg_id = b.stg_id;

      GET DIAGNOSTICS deleted_rows = ROW_COUNT;
      total_deleted := total_deleted + deleted_rows;

      RAISE NOTICE 'Batch % to %: inserted/updated %, deleted % staging rows',
                   v_start, v_end, cur_rows, deleted_rows;

      v_ok := true;
    EXCEPTION WHEN OTHERS THEN
      RAISE WARNING 'Error processing batch % to %: % (SQLSTATE %)',
                    v_start, v_end, SQLERRM, SQLSTATE;
      v_ok := false;
    END;

    IF v_ok THEN
      COMMIT;
    ELSE
      ROLLBACK;
    END IF;
    v_start := v_end + 1;
  END LOOP;

  RAISE NOTICE 'load_prices_from_staged_batched: total inserted/updated %, total deleted from staging %',
               inserted_rows, total_deleted;
END;
$$;

COMMIT;
------------------------Resolve the price_observation rows with the new product_source_id reference, and clean up orphan records that can't be resolved (should be very few if any after the dim_price_observation -> staging load procedure is fixed to populate product_source_id directly)

CREATE OR REPLACE FUNCTION pricing.resolve_price_rejects(
    p_limit int DEFAULT 50000,
    p_only_unresolved boolean DEFAULT true
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
  v_source_id       smallint;
  v_mtg_game_id     smallint;
  v_inserted        bigint := 0;
  v_selected        bigint := 0;
  v_print_id        bigint := 0;
  v_external_id     bigint := 0;
  v_set_collector   bigint := 0;
  v_unresolved      bigint := 0;
  v_terminal_scry   bigint := 0;
BEGIN
  -- mtgstock source
  SELECT ps.source_id INTO v_source_id
  FROM pricing.price_source ps
  WHERE ps.code = 'mtgstocks';

  IF v_source_id IS NULL THEN
    RAISE EXCEPTION 'Missing source_code=mtgstocks in pricing.price_source';
  END IF;

  -- MTG game id
  SELECT cg.game_id INTO v_mtg_game_id
  FROM card_catalog.card_games_ref cg
  WHERE lower(cg.code) IN ('mtg', 'magic', 'magic_the_gathering')
  ORDER BY CASE lower(cg.code) WHEN 'mtg' THEN 1 ELSE 2 END
  LIMIT 1;

  IF v_mtg_game_id IS NULL THEN
    RAISE EXCEPTION 'Could not resolve MTG game_id';
  END IF;

  -- pick a working set
  DROP TABLE IF EXISTS tmp_rejects;
  CREATE TEMP TABLE tmp_rejects ON COMMIT DROP AS
  SELECT *
  FROM pricing.stg_price_observation_reject r
  WHERE (NOT p_only_unresolved) OR (r.resolved_at IS NULL AND is_terminal IS FALSE)
  ORDER BY r.resolution_attempted_at
  LIMIT p_limit;

  SELECT COUNT(*) INTO v_selected FROM tmp_rejects;
  RAISE NOTICE 'resolve_price_rejects: selected % candidates (only_unresolved=%)', v_selected, p_only_unresolved;

  --check first if the id is marked as migrated or merged in the migration tables (in case the reject was from a previous run and the dim_price_observation load procedure was fixed in the meantime to populate product_source_id directly)

  -- 1) resolve card_version_id (print_id, external ids, fallback)
  DROP TABLE IF EXISTS tmp_resolved;
  CREATE TEMP TABLE tmp_resolved ON COMMIT DROP AS
  WITH map_print AS (
    SELECT DISTINCT r.print_id, cei.card_version_id
    FROM tmp_rejects r
    JOIN card_catalog.card_identifier_ref cir
      ON cir.identifier_name = 'mtgstock_id'
    JOIN card_catalog.card_external_identifier cei
      ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
     AND cei.value = r.print_id::text
  ),

  map_ext AS (
    WITH candidates AS (
      SELECT r.print_id
      , 'scryfall_id'::text AS identifier_name
      , COALESCE(m.new_scryfall_id::text, r.scryfall_id) AS identifier_value
      , 1 AS prio
      FROM tmp_rejects r
      LEFT JOIN card_catalog.scryfall_migration m
        ON NULLIF(r.scryfall_id,'')::uuid = m.old_scryfall_id
        AND m.migration_strategy IN ('merge', 'move')   -- add other “redirect” strategies you store
        AND m.new_scryfall_id IS NOT NULL
        
      WHERE r.scryfall_id IS NOT NULL AND r.scryfall_id <> ''
      UNION ALL
      SELECT r.print_id, 'tcgplayer_id', r.tcg_id, 2
      FROM tmp_rejects r WHERE r.tcg_id IS NOT NULL AND r.tcg_id <> ''
      UNION ALL
      SELECT r.print_id, 'cardtrader_id', r.cardtrader_id, 3
      FROM tmp_rejects r WHERE r.cardtrader_id IS NOT NULL AND r.cardtrader_id <> ''
    ),
    joined AS (
      SELECT c.print_id, c.prio, cei.card_version_id
      FROM candidates c
      JOIN card_catalog.card_identifier_ref cir
        ON cir.identifier_name = c.identifier_name
      JOIN card_catalog.card_external_identifier cei
        ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
       AND cei.value = c.identifier_value
    ),
    ranked AS (
      SELECT *, row_number() OVER (PARTITION BY print_id ORDER BY prio) rn
      FROM joined
    )
    SELECT print_id, card_version_id
    FROM ranked
    WHERE rn = 1
  ),
  map_fb AS (
    SELECT DISTINCT r.set_abbr, r.collector_number, cv.card_version_id
    FROM tmp_rejects r
    JOIN card_catalog.sets s
      ON LOWER(s.set_code) = LOWER(r.set_abbr)
    JOIN card_catalog.card_version cv
      ON cv.set_id = s.set_id
     AND cv.collector_number::text = r.collector_number
    LEFT JOIN card_catalog.unique_cards_ref uc
      ON uc.unique_card_id = cv.unique_card_id
    WHERE r.set_abbr IS NOT NULL
      AND r.collector_number IS NOT NULL
      AND (
          r.card_name IS NULL
          OR uc.card_name IS NULL
          OR lower(uc.card_name) = lower(r.card_name)
          OR lower(r.card_name) LIKE (lower(uc.card_name) || ' (%')
      )
  )
  SELECT
    r.*,
    COALESCE(mp.card_version_id, me.card_version_id, mf.card_version_id) AS card_version_id,
    CASE
      WHEN mp.card_version_id IS NOT NULL THEN 'PRINT_ID'
      WHEN me.card_version_id IS NOT NULL THEN 'EXTERNAL_ID'
      WHEN mf.card_version_id IS NOT NULL THEN 'SET_COLLECTOR'
      ELSE 'UNRESOLVED'
    END AS resolution_method
  FROM tmp_rejects r
  LEFT JOIN map_print mp ON mp.print_id = r.print_id
  LEFT JOIN map_ext   me ON me.print_id = r.print_id
  LEFT JOIN map_fb    mf ON mf.set_abbr = r.set_abbr AND mf.collector_number = r.collector_number;

  SELECT
    COUNT(*) FILTER (WHERE resolution_method = 'PRINT_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'EXTERNAL_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'SET_COLLECTOR'),
    COUNT(*) FILTER (WHERE resolution_method = 'UNRESOLVED')
  INTO v_print_id, v_external_id, v_set_collector, v_unresolved
  FROM tmp_resolved;
  RAISE NOTICE 'resolve_price_rejects: PRINT_ID=% EXTERNAL_ID=% SET_COLLECTOR=% UNRESOLVED=%',
    v_print_id, v_external_id, v_set_collector, v_unresolved;

  -- 1b) Back-fill mtgstock_id mapping for rows resolved via EXTERNAL_ID or
  --     SET_COLLECTOR (PRINT_ID rows are already in card_external_identifier).
  --     Mirrors the equivalent block in load_staging_prices_batched.
  WITH resolved_prints AS (
    SELECT DISTINCT
      r.print_id,
      r.card_version_id
    FROM tmp_resolved r
    WHERE r.card_version_id IS NOT NULL
      AND r.resolution_method <> 'PRINT_ID'
  ),
  unambiguous_print AS (
    SELECT rp.print_id, rp.card_version_id
    FROM resolved_prints rp
    JOIN (
      SELECT print_id
      FROM resolved_prints
      GROUP BY print_id
      HAVING count(DISTINCT card_version_id) = 1
    ) ok USING (print_id)
  ),
  -- choose at most one print_id per card_version_id to avoid PK conflicts
  pick_one_per_cv AS (
    SELECT DISTINCT ON (card_version_id)
      card_version_id,
      print_id::text AS print_value
    FROM unambiguous_print
    ORDER BY card_version_id, print_id
  ),
  mtgstock_ref AS (
    SELECT card_identifier_ref_id
    FROM card_catalog.card_identifier_ref
    WHERE identifier_name = 'mtgstock_id'
    LIMIT 1
  )
  INSERT INTO card_catalog.card_external_identifier (card_identifier_ref_id, card_version_id, value)
  SELECT
    r.card_identifier_ref_id,
    p.card_version_id,
    p.print_value
  FROM pick_one_per_cv p
  CROSS JOIN mtgstock_ref r
  LEFT JOIN card_catalog.card_external_identifier existing_pk
    ON existing_pk.card_version_id = p.card_version_id
   AND existing_pk.card_identifier_ref_id = r.card_identifier_ref_id
  WHERE existing_pk.card_version_id IS NULL
  ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING;

  -- 2) ensure product_ref + mtg_card_products for newly resolved card_version_id
  WITH need AS (
    SELECT DISTINCT card_version_id
    FROM tmp_resolved
    WHERE card_version_id IS NOT NULL
    EXCEPT
    SELECT card_version_id FROM pricing.mtg_card_products
  ),
  gen AS (
    SELECT card_version_id, uuid_generate_v4() AS product_id
    FROM need
  ),
  ins_prod AS (
    INSERT INTO pricing.product_ref (product_id, game_id)
    SELECT product_id, v_mtg_game_id
    FROM gen
    ON CONFLICT (product_id) DO NOTHING
  )
  INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
  SELECT product_id, card_version_id
  FROM gen
  ON CONFLICT (card_version_id) DO NOTHING;

  -- 3) ensure source_product
  INSERT INTO pricing.source_product (product_id, source_id)
  SELECT DISTINCT mcp.product_id, v_source_id
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  LEFT JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
  WHERE r.card_version_id IS NOT NULL
    AND sp.source_product_id IS NULL
  ON CONFLICT (product_id, source_id) DO NOTHING;

  -- 4) re-feed resolved rejects into stg_price_observation (wide model).
  --    ts_date / data_provider_id are NOT NULL on staging; product_id is UUID.
  --    list_count / sold_count do not exist on staging (they are fact-only).
  --    Rows where all three cents columns are NULL are skipped to match the
  --    downstream procedure's filter and avoid orphan no-op staging rows.
  INSERT INTO pricing.stg_price_observation (
    ts_date, game_code, print_id,
    list_low_cents, list_avg_cents, sold_avg_cents,
    is_foil, source_code, data_provider_id, value,
    product_id, card_version_id, source_product_id,
    set_abbr, collector_number, card_name, scryfall_id, tcg_id,
    scraped_at
  )
  SELECT
    r.ts_date,
    r.game_code,
    r.print_id,
    r.list_low_cents,
    r.list_avg_cents,
    r.sold_avg_cents,
    r.is_foil,
    r.source_code,
    r.data_provider_id,
    r.value,
    mcp.product_id,
    r.card_version_id,
    sp.source_product_id,
    r.set_abbr,
    r.collector_number,
    r.card_name,
    r.scryfall_id,
    r.tcg_id,
    r.scraped_at
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
  WHERE r.card_version_id IS NOT NULL
    AND NOT (r.list_low_cents IS NULL
         AND r.list_avg_cents IS NULL
         AND r.sold_avg_cents IS NULL);

  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  RAISE NOTICE 'resolve_price_rejects: re-fed % rows into stg_price_observation', v_inserted;

  -- 5) mark resolved rejects as terminal. Natural match key in the wide
  --    model: (ts_date, print_id, is_foil, source_code, data_provider_id,
  --    scraped_at) — one reject row per scrape per (day, product, foil,
  --    provider). If that is not unique in your data, add a surrogate PK
  --    on stg_price_observation_reject.
  UPDATE pricing.stg_price_observation_reject rej
  SET
    resolved_at                = now(),
    resolved_card_version_id   = r.card_version_id,
    resolved_method            = r.resolution_method,
    resolved_product_id        = mcp.product_id,
    resolved_source_product_id = sp.source_product_id,
    is_terminal                = TRUE,
    terminal_reason            = 'Resolved via ' || r.resolution_method || ' mapping'
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
  WHERE rej.ts_date          = r.ts_date
    AND rej.print_id         = r.print_id
    AND rej.is_foil          = r.is_foil
    AND rej.source_code      = r.source_code
    AND rej.data_provider_id = r.data_provider_id
    AND rej.scraped_at       = r.scraped_at
    AND r.card_version_id IS NOT NULL;

  UPDATE pricing.stg_price_observation_reject r
  SET
  resolved_at = now(),
  is_terminal = TRUE,
  terminal_reason = 'Scryfall migration delete and no alternative identifiers'
  FROM card_catalog.scryfall_migration m
  WHERE m.migration_strategy = 'delete'
  AND m.old_scryfall_id::text = r.scryfall_id;

  GET DIAGNOSTICS v_terminal_scry = ROW_COUNT;
  RAISE NOTICE 'resolve_price_rejects: marked % rows terminal (scryfall delete)', v_terminal_scry;

  RETURN v_inserted;
END;
$$;