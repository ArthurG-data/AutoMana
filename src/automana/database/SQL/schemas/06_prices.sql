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
  ('NONFOIL', 'Nonfoil'),
  ('FOIL',    'Foil'),
  ('ETCHED',  'Etched')
ON CONFLICT (code) DO NOTHING;

INSERT INTO pricing.price_source (code, name, currency_code) VALUES  
  ('tcg', 'tcgplayer', 'USD'),
  ('cardkingdom', 'Card Kingdom', 'USD'),
  ('cardmarket', 'Cardmarket', 'EUR'),
  ('starcitygames', 'Star City Games', 'USD'),
  ('ebay', 'eBay', 'USD'),
  ('amazon', 'Amazon', 'USD')
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

--TIer 2: daily -> 5 years

CREATE TABLE IF NOT EXISTS  pricing.print_price_daily (
    card_version_id UUID NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),

    transaction_type_id INTEGER NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),

    condition_id SMALLINT NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),

    language_id SMALLINT NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    finish_id SMALLINT NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),  -- verify table name

    price_date DATE NOT NULL,

    min_price    INTEGER,
    max_price    INTEGER,
    median_price INTEGER,
    p25_price    INTEGER,
    p75_price    INTEGER,
    avg_price    INTEGER,
    n_sources    SMALLINT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT print_price_daily_pk
        PRIMARY KEY (card_version_id, price_date, transaction_type_id, finish_id, condition_id, language_id),

    CONSTRAINT chk_sources_nonneg
        CHECK (n_sources IS NULL OR n_sources >= 0),

    CONSTRAINT chk_min_le_max
        CHECK (min_price IS NULL OR max_price IS NULL OR min_price <= max_price),

    CONSTRAINT chk_prices_nonneg
        CHECK (
          (min_price IS NULL OR min_price >= 0) AND
          (max_price IS NULL OR max_price >= 0) AND
          (median_price IS NULL OR median_price >= 0) AND
          (avg_price IS NULL OR avg_price >= 0)
        )
);

COMMENT ON COLUMN pricing.print_price_daily.median_price IS 'Price in cents (USD)';
COMMENT ON COLUMN pricing.print_price_daily.p25_price IS '25th percentile price in cents (USD)';
COMMENT ON COLUMN pricing.print_price_daily.p75_price IS '75th percentile price in cents (USD)';
-- Fast “give me all cards for date range + type (+dims if you filter)”
CREATE INDEX IF NOT EXISTS idx_ppd_date_type_dims
ON pricing.print_price_daily (price_date, transaction_type_id, finish_id, condition_id, language_id);

-- Fast “chart one card over time for a type (+dims)”
CREATE INDEX IF NOT EXISTS idx_ppd_card_dims_type_date
ON pricing.print_price_daily (card_version_id, transaction_type_id, finish_id, condition_id, language_id, price_date);
-------------------------------------------------------------------------------
--Tier 3: weekly aggre for older than 5 years
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pricing.print_price_weekly (
    card_version_id UUID NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),

    transaction_type_id INTEGER NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),

    condition_id SMALLINT NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),

    language_id SMALLINT NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    finish_id SMALLINT NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),  -- verify table name

    price_week DATE NOT NULL, -- we can define this as the Monday of the week for consistency

    min_price    INTEGER,
    max_price    INTEGER,
    median_price INTEGER,
    p25_price    INTEGER,
    p75_price    INTEGER,
    avg_price    INTEGER,
    n_sources    SMALLINT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT print_price_weekly_pk
        PRIMARY KEY (card_version_id, price_week, transaction_type_id, finish_id, condition_id, language_id),

    CONSTRAINT chk_sources_nonneg
        CHECK (n_sources IS NULL OR n_sources >= 0),

    CONSTRAINT chk_min_le_max
        CHECK (min_price IS NULL OR max_price IS NULL OR min_price <= max_price),

    CONSTRAINT chk_prices_nonneg
        CHECK (
          (min_price IS NULL OR min_price >= 0) AND
          (max_price IS NULL OR max_price >= 0) AND
          (median_price IS NULL OR median_price >= 0) AND
          (avg_price IS NULL OR avg_price >= 0)
        )
);
-- NOTE: print_price_weekly was defined here but was NEVER applied to the live DB.
-- It also contained a SQL syntax error (ADD COMMENT is not valid PostgreSQL; must be COMMENT ON TABLE).
-- Fixed syntax below. Create via a new migration (16_+) if this table is needed.
COMMENT ON TABLE pricing.print_price_weekly IS 'Weekly aggregated price metrics for each card_version_id + transaction_type + dimensions, for older data beyond the daily retention period. price_week is the Monday of the week.';

CREATE INDEX IF NOT EXISTS idx_ppw_week_type_dims
ON pricing.print_price_weekly (price_week, transaction_type_id, finish_id, condition_id, language_id);
CREATE INDEX IF NOT EXISTS idx_ppw_card_dims_type_week
ON pricing.print_price_weekly (card_version_id, transaction_type_id, finish_id, condition_id, language_id, price_week);
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
CREATE TABLE pricing.stg_price_observation (
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
---------------------------------------------------------------------------------------------new

  CREATE INDEX IF NOT EXISTS raw_mtg_stock_price_ts_date_idx
  ON pricing.raw_mtg_stock_price (ts_date);

  -- identifier lookup accelerators
  CREATE INDEX IF NOT EXISTS card_identifier_ref_name_idx
  ON card_catalog.card_identifier_ref (identifier_name, card_identifier_ref_id);

  CREATE INDEX IF NOT EXISTS card_external_identifier_ref_value_idx
  ON card_catalog.card_external_identifier (card_identifier_ref_id, value);

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
CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched(source_name VARCHAR(20), batch_days int DEFAULT 30)--drop first
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

BEGIN
  -- determine overall date range from raw data
  SET LOCAL work_mem = '512MB';
  SET LOCAL maintenance_work_mem = '1GB';
  SET LOCAL temp_buffers = '256MB';
  SET LOCAL synchronous_commit = off;

  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM pricing.raw_mtg_stock_price;
  IF v_min IS NULL THEN
    RAISE NOTICE 'load_staging_prices_batched: no rows in raw_mtg_stock_price';
    RETURN;
  END IF;

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
-----------------------------------------------
  SELECT cg.game_id INTO v_mtg_game_id
  FROM card_catalog.card_games_ref cg
  WHERE lower(cg.code) IN ('mtg', 'magic', 'magic_the_gathering')
  ORDER BY CASE lower(cg.code) WHEN 'mtg' THEN 1 ELSE 2 END
  LIMIT 1;

  EXECUTE $sql$
    CREATE TABLE IF NOT EXISTS pricing.stg_price_observation_reject (
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
  $sql$;

  v_start := v_min;
  WHILE v_start <= v_max LOOP
    v_end := LEAST(v_start + (batch_days - 1), v_max);
    v_ok :=false;
    BEGIN
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
        v.data_provider_id
      FROM tmp_raw_batch r
      CROSS JOIN LATERAL (VALUES
        (r.price_low,          false, r.price_low),
        (r.price_avg,          false, r.price_avg),
        (r.price_avg,           true, r.price_foil),
        (r.price_market,       false, r.price_market),
        (r.price_market,        true, r.price_market_foil)
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
    ON sr.set_code = u.set_abbr
  JOIN card_catalog.card_version cv
    ON cv.set_id = sr.set_id
  AND cv.collector_number::text = u.collector_number
  LEFT JOIN card_catalog.unique_cards_ref uc
    ON uc.unique_card_id = cv.unique_card_id
  WHERE u.set_abbr IS NOT NULL
    AND u.collector_number IS NOT NULL
    AND (u.card_name IS NULL OR uc.card_name IS NULL OR lower(uc.card_name) = lower(u.card_name));

  -- 3d) Final resolved rows
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
  FROM tmp_raw_batch u
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
  ON CONFLICT DO NOTHING;

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
          l.product_id::text,
          r.card_version_id::text,
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

      RAISE NOTICE 'Inserted % rows for batch', cur_rows;
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
      v_start := v_end + 1;
  END LOOP;
  CREATE INDEX IF NOT EXISTS stg_price_obs_date_spid_foil_idx
  ON pricing.stg_price_observation (ts_date, source_product_id, is_foil);
  RAISE NOTICE 'load_staging_prices_batched: total inserted % rows', total_inserted;
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
        CASE WHEN s.is_foil THEN v_finish_foil_id
             ELSE v_finish_default_id END             AS finish_id,
        v_condition_id                                AS condition_id,
        v_language_id                                 AS language_id,
        s.list_low_cents,
        s.list_avg_cents,
        s.sold_avg_cents,
        s.scraped_at
      FROM pricing.stg_price_observation s
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
  v_source_id smallint;
  v_mtg_game_id smallint;
  v_inserted bigint := 0;
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
  WHERE (NOT p_only_unresolved) OR r.resolved_at IS NULL AND is_terminal IS FALSE
  ORDER BY r.resolution_attempted_at
  LIMIT p_limit;

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
      ON s.set_code = r.set_abbr
    JOIN card_catalog.card_version cv
      ON cv.set_id = s.set_id
     AND cv.collector_number::text = r.collector_number
    LEFT JOIN card_catalog.unique_cards_ref uc
      ON uc.unique_card_id = cv.unique_card_id
    WHERE r.set_abbr IS NOT NULL
      AND r.collector_number IS NOT NULL
      AND (r.card_name IS NULL OR uc.card_name IS NULL OR lower(uc.card_name) = lower(r.card_name))
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



  RETURN v_inserted;
END;
$$;