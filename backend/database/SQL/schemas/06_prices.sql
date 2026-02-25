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
CREATE TABLE IF NOT EXISTS pricing.price_source (
  source_id   SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'tcgplayer','cardkingdom','ebay','amazon', etc.
  currency_code VARCHAR(3) NOT NULL DEFAULT 'USD' REFERENCES pricing.currency_ref(currency_code),
  name       TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
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

INSERT INTO pricing.price_source (code, name) VALUES  
  ('mtgstocks', 'MTG Stock')
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
CREATE TABLE IF NOT EXISTS pricing.price_observation (
    ts_date DATE NOT NULL,
    metric_id SMALLINT NOT NULL REFERENCES pricing.price_metric(metric_id),
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

    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_product_id BIGINT NOT NULL REFERENCES pricing.source_product(source_product_id),
    value NUMERIC(12,4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ts_date, source_product_id, metric_id, price_type_id, finish_id, condition_id, language_id)
);
-- -------------------------------------------create hypertable
SELECT create_hypertable('pricing.price_observation',
                         by_range('ts_date'),
                         if_not_exists => TRUE);

-- Add a space (hash) dimension on source_product_id for parallelism & chunk fan-out:
--not good for one diskSELECT add_dimension('pricing.price_observation', 'source_product_id', number_partitions => 8);

--set chunk time
SELECT set_chunk_time_interval('pricing.price_observation', INTERVAL '30 days');

CREATE INDEX IF NOT EXISTS idx_price_date ON pricing.price_observation(source_product_id, ts_date DESC);


ALTER TABLE pricing.price_observation
  SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'source_product_id',
       timescaledb.compress_orderby   = 'ts_date DESC');

-- Auto-compress anything older than 180 days:
SELECT add_compression_policy('pricing.price_observation', INTERVAL '180 days');



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
ADD COMMENT ON TABLE pricing.raw_mtg_stock_price IS 'Raw price data ingested from MTG Stocks, with one row per print_id and date, and multiple price metrics as columns. This is the landing table before transformation and loading into the dimensional model.';
CREATE INDEX idx_raw_price_date ON pricing.raw_mtg_stock_price(print_id, ts_date);
DROP TABLE IF EXISTS pricing.stg_price_observation;
CREATE TABLE pricing.stg_price_observation (
game_code     TEXT       NOT NULL,
print_id      BIGINT      NOT NULL,
metric_code     TEXT    NOT NULL,
is_foil       BOOLEAN    NOT NULL,
source_code     TEXT    NOT NULL,
value         NUMERIC(12,4) NOT NULL,
product_id TEXT NOT NULL,
card_version_id TEXT,
source_product_id BIGINT, --new
set_abbr TEXT,
collector_number TEXT,
card_name TEXT,
scryfall_id TEXT,
tcg_id TEXT,
scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
---------------------------------------------------------------------------------------------new
DROP TABLE IF EXISTS pricing.dim_price_observation;--need rerok
CREATE TABLE IF NOT EXISTS pricing.dim_price_observation (
  ts_date       DATE        NOT NULL,
  metric_id     SMALLINT    NOT NULL,
  product_source_id BIGINT      NOT NULL, --new 
  value         NUMERIC(12,4) NOT NULL,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
);
CREATE TABLE IF NOT EXISTS pricing.orphan_price_observation (
  print_id      BIGINT      NOT NULL,
  source_id     SMALLINT    NOT NULL,
  metric_id     SMALLINT    NOT NULL,
  ts_date       DATE        NOT NULL,
  value         NUMERIC(12,4) NOT NULL,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  COMMENT "This table capture the price observation not linked to any card in card_version, to be used for debugging and data quality checks"
);

















------------------------------------------------------------------
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
--translate code to id
CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched(batch_days int DEFAULT 30)
LANGUAGE plpgsql
AS $$
DECLARE
  v_min date;
  v_max date;
  v_start date;
  v_end   date;
  v_source_id SMALLINT;
  v_mtg_game_id SMALLINT;
  cur_rows bigint;
  total_inserted bigint := 0;
BEGIN
  -- determine overall date range from raw data
  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM pricing.raw_mtg_stock_price;
  IF v_min IS NULL THEN
    RAISE NOTICE 'load_staging_prices_batched: no rows in raw_mtg_stock_price';
    RETURN;
  END IF;

  --will need to add the foil code translation in the same way as the metric code and source code translation
  SELECT ps.source_id INTO v_source_id
  FROM pricing.price_source ps
  WHERE ps.code = 'mtgstocks';

  IF v_source_id IS NULL THEN
    RAISE EXCEPTION 'Missing source_code=mtgstocks in pricing.price_source';
  END IF;

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
      scraped_at timestamptz NOT NULL,
      metric_code text NOT NULL,
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
      s.cardtrader_id
    FROM pricing.raw_mtg_stock_price s
    WHERE s.ts_date >= v_start
      AND s.ts_date <= v_end;

    DROP TABLE IF EXISTS tmp_unpivot;
    CREATE TEMP TABLE tmp_unpivot ON COMMIT DROP AS
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

      v.metric_code,
      v.is_foil,
      v.value
    FROM tmp_raw_batch r
    CROSS JOIN LATERAL (VALUES
      ('price_low',          false, r.price_low),
      ('price_avg',          false, r.price_avg),
      ('price_avg',           true, r.price_foil),
      ('price_market',       false, r.price_market),
      ('price_market',        true, r.price_market_foil)
    ) AS v(metric_code, is_foil, value)
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
FROM tmp_unpivot u
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
  SELECT u.print_id, 'scryfall_id'::text   AS identifier_name, u.scryfall_id   AS identifier_value, 1 AS prio
  FROM tmp_unpivot u WHERE u.scryfall_id IS NOT NULL

  UNION ALL
  SELECT u.print_id, 'tcgplayer_id'::text  AS identifier_name, u.tcg_id        AS identifier_value, 2 AS prio
  FROM tmp_unpivot u WHERE u.tcg_id IS NOT NULL

  UNION ALL
  SELECT u.print_id, 'cardtrader_id'::text AS identifier_name, u.cardtrader_id AS identifier_value, 3 AS prio
  FROM tmp_unpivot u WHERE u.cardtrader_id IS NOT NULL
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
FROM tmp_unpivot u
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
FROM tmp_unpivot u
LEFT JOIN tmp_map_print mp
  ON mp.print_id = u.print_id
LEFT JOIN tmp_map_external me
  ON me.print_id = u.print_id
LEFT JOIN tmp_map_fallback mf
  ON mf.set_abbr = u.set_abbr
 AND mf.collector_number = u.collector_number;

    -- -------------------------------------------------------------------------
    -- 4) Send unresolved rows to reject table (so you can inspect/repair mappings)
    -- -------------------------------------------------------------------------
    INSERT INTO pricing.stg_price_observation_reject (
      ts_date, game_code, print_id, source_code, scraped_at,
      metric_code, is_foil, value,
      card_name, set_abbr, collector_number, scryfall_id, tcg_id, cardtrader_id,
      reject_reason
    )
    SELECT
      r.ts_date, r.game_code, r.print_id, r.source_code, r.scraped_at,
      r.metric_code, r.is_foil, r.value,
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
    INSERT INTO pricing.stg_price_observation (
      game_code, print_id, metric_code, is_foil, source_code, value,
      product_id, source_product_id, scraped_at
    )
    SELECT
      r.game_code,
      r.print_id,
      r.metric_code,
      r.is_foil,
      r.source_code,
      r.value,
      l.product_id::text,
      l.source_product_id,
      r.scraped_at
    FROM tmp_resolved r
    JOIN tmp_sp_lookup l
      ON l.card_version_id = r.card_version_id
    WHERE r.card_version_id IS NOT NULL;

    GET DIAGNOSTICS cur_rows = ROW_COUNT;
    total_inserted := total_inserted + cur_rows;

    RAISE NOTICE 'Inserted % rows for batch', cur_rows;

  
    -- advance to next batch
    v_start := v_end + 1;
  END LOOP;

  RAISE NOTICE 'load_staging_prices_batched: total inserted % rows', total_inserted;
END;
$$;

-----------------------------------------------------------------good until here 

CREATE INDEX IF NOT EXISTS dim_price_obs_ts_idx
  ON pricing.dim_price_observation (ts_date);

CREATE OR REPLACE PROCEDURE pricing.create_product_source()
LANGUAGE plpgsql
AS $$
BEGIN
  CREATE TEMP TABLE temp_missing_ids (
        print_id BIGINT,
        scryfall_id UUID,
        multiverse_id BIGINT,
        tcg_id BIGINT,
        error_reason TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    ) ON COMMIT PRESERVE ROWS;

    --decompress chunks if needed (uncomment if you need to decompress chunks to update the data, but be careful with large datasets)

    -- Fetch source_id once
    SELECT ps.source_id INTO v_source_id
    FROM pricing.price_source ps
    WHERE ps.code = 'mtgstocks';

    -- Fetch game IDs
    SELECT game_id INTO v_card_game_id
    FROM card_catalog.card_games_ref
    WHERE code = 'mtg';

    SELECT game_id INTO v_game_id
    FROM card_catalog.games_ref
    WHERE game_description = 'paper';

    IF v_source_id IS NULL THEN
        RAISE EXCEPTION 'price_source with code=% not found', 'mtgstocks';
    END IF;

    -- Iterate dict: key=print_id, value={...}
    FOR kv IN
        SELECT key, value
        FROM jsonb_each(records)
    LOOP
        v_total_records := v_total_records + 1;
        
        BEGIN
            -- Parse print_id from key
            v_print_id := kv.key::BIGINT;

            -- Parse identifiers from value object
            v_scryfall_id   := NULLIF(kv.value->>'scryfall_id', '')::UUID;
            v_multiverse_id := NULLIF(kv.value->>'multiverse_id', '')::BIGINT;
            v_tcg_id        := NULLIF(kv.value->>'tcg_id', '')::BIGINT;

            v_card_version_id := NULL;

            -- Resolve card_version_id (priority: scryfall -> tcg -> multiverse)
            IF v_scryfall_id IS NOT NULL THEN
                SELECT cei.card_version_id INTO v_card_version_id
                FROM card_catalog.card_external_identifier cei
                JOIN card_catalog.card_identifier_ref cir
                  ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                WHERE cir.identifier_name = 'scryfall_id'
                  AND cei.value = v_scryfall_id::text
                LIMIT 1;
            END IF;

            IF v_card_version_id IS NULL AND v_tcg_id IS NOT NULL THEN
                SELECT cei.card_version_id INTO v_card_version_id
                FROM card_catalog.card_external_identifier cei
                JOIN card_catalog.card_identifier_ref cir
                  ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                WHERE cir.identifier_name = 'tcgplayer_id'
                  AND cei.value = v_tcg_id::text
                LIMIT 1;
            END IF;

            IF v_card_version_id IS NULL AND v_multiverse_id IS NOT NULL THEN
                SELECT cei.card_version_id INTO v_card_version_id
                FROM card_catalog.card_external_identifier cei
                JOIN card_catalog.card_identifier_ref cir
                  ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                WHERE cir.identifier_name = 'multiverse_id'
                  AND cei.value = v_multiverse_id::text
                LIMIT 1;
            END IF;

            -- If card_version_id not found, log and continue
            IF v_card_version_id IS NULL THEN
                INSERT INTO temp_missing_ids (print_id, scryfall_id, multiverse_id, tcg_id, error_reason)
                VALUES (v_print_id, v_scryfall_id, v_multiverse_id, v_tcg_id, 
                        'No card_version_id found for any identifier');
                v_missing_count := v_missing_count + 1;
                CONTINUE;  -- Skip to next record
            END IF;

            -- Get or create product_id for this card_version_id
            v_product_id := NULL;
            SELECT mcp.product_id INTO v_product_id
            FROM pricing.mtg_card_products mcp
            WHERE mcp.card_version_id = v_card_version_id
            LIMIT 1;

            IF v_product_id IS NULL THEN
                -- Create product_ref
                INSERT INTO pricing.product_ref (game_id)
                VALUES (v_game_id)
                RETURNING product_id INTO v_created_product_id;

                -- Try to link card_version -> product
                INSERT INTO pricing.mtg_card_products (product_id, game_version_id, card_version_id)
                VALUES (v_created_product_id, v_game_id, v_card_version_id)
                ON CONFLICT (card_version_id) DO NOTHING;

                -- Reuse existing product_id if conflict
                SELECT mcp.product_id INTO v_product_id
                FROM pricing.mtg_card_products mcp
                WHERE mcp.card_version_id = v_card_version_id
                LIMIT 1;

                -- Cleanup orphan if needed
                IF v_product_id IS DISTINCT FROM v_created_product_id THEN
                    DELETE FROM pricing.product_ref pr
                    WHERE pr.product_id = v_created_product_id
                      AND NOT EXISTS (SELECT 1 FROM pricing.mtg_card_products m WHERE m.product_id = v_created_product_id)
                      AND NOT EXISTS (SELECT 1 FROM pricing.source_product sp WHERE sp.product_id = v_created_product_id);
                END IF;
            END IF;

            IF v_product_id IS NULL THEN
                INSERT INTO temp_missing_ids (print_id, scryfall_id, multiverse_id, tcg_id, error_reason)
                VALUES (v_print_id, v_scryfall_id, v_multiverse_id, v_tcg_id, 
                        'Failed to create/resolve product_id');
                v_missing_count := v_missing_count + 1;
                CONTINUE;
            END IF;

            -- Upsert source_product
            INSERT INTO pricing.source_product (product_id, source_id)
            VALUES (v_product_id, v_source_id)
            ON CONFLICT (product_id, source_id)
            DO UPDATE SET product_id = EXCLUDED.product_id
            RETURNING source_product_id INTO v_source_product_id;

            -- Update price_observation
            UPDATE pricing.price_observation po
            SET source_product_id = v_source_product_id
            WHERE po.print_id = v_print_id
              AND po.source_id = v_source_id;

            GET DIAGNOSTICS v_last_update_count = ROW_COUNT;
            v_rows_updated := v_rows_updated + v_last_update_count;

        SELECT compress_chunk(i) 
        FROM show_chunks('pricing.price_observation', 'oldest');
        
        EXCEPTION WHEN OTHERS THEN
            -- Catch any other errors and log them
            INSERT INTO temp_missing_ids (print_id, scryfall_id, multiverse_id, tcg_id, error_reason)
            VALUES (v_print_id, v_scryfall_id, v_multiverse_id, v_tcg_id, 
                    'Exception: ' || SQLERRM);
            v_missing_count := v_missing_count + 1;
            CONTINUE;
        END;

    END LOOP;

    -- Final report
    RAISE NOTICE 'Migration Summary: Total=%, Updated=%, Missing/Failed=%',
        v_total_records, v_rows_updated, v_missing_count;

    -- Show missing IDs if any
    IF v_missing_count > 0 THEN
        RAISE NOTICE 'Missing IDs stored in temp_missing_ids table. Query with: SELECT * FROM temp_missing_ids;';
    END IF;

END;
 $$;


CREATE OR REPLACE PROCEDURE pricing.load_prices_from_dim_batched(batch_days int DEFAULT 30)
LANGUAGE plpgsql
AS $$
DECLARE
  v_min date;
  v_max date;
  v_start date;
  v_end   date;
  inserted_rows bigint := 0;
  cur_rows bigint;
BEGIN
  -- Fast session knobs (reset automatically after proc)
  PERFORM set_config('synchronous_commit','off', true);
  PERFORM set_config('work_mem','256MB', true);
  PERFORM set_config('maintenance_work_mem','2047MB', true);
  PERFORM set_config('max_parallel_workers_per_gather','4', true);

  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM dim_price_observation;
  IF v_min IS NULL THEN
    RAISE NOTICE 'No rows in dim_price_observation.';
    RETURN;
  END IF;
  RAISE NOTICE 'Loading prices from dim table for dates % to %', v_min, v_max;
  -- Reduce write-time overhead on target
  DROP INDEX IF EXISTS public.idx_price_date;
  ALTER TABLE pricing.price_observation SET (autovacuum_enabled = off);

  v_start := v_min;
  WHILE v_start <= v_max LOOP
    v_end := LEAST(v_start + (batch_days - 1), v_max);

    RAISE NOTICE 'Loading batch % to %', v_start, v_end;

    -- Dedup this time slice only (cheaper memory footprint)
    CREATE TEMP TABLE _dedup ON COMMIT DROP AS
    SELECT *
    FROM (
      SELECT d.*,
             row_number() OVER (
               PARTITION BY print_id, source_id, metric_id, ts_date
               ORDER BY scraped_at DESC
             ) AS rn
      FROM pricing.dim_price_observation d
      WHERE d.ts_date >= v_start AND d.ts_date <= v_end
    ) x
    WHERE rn = 1;

    CREATE INDEX ON _dedup (ts_date);

    -- Insert in time order to keep inserts chunk-local
    INSERT INTO pricing.price_observation (ts_date, game_id, print_id, source_id, metric_id, value, scraped_at)
    SELECT ts_date, game_id, print_id, source_id, metric_id, value, scraped_at
    FROM _dedup
    ORDER BY ts_date;

    GET DIAGNOSTICS cur_rows = ROW_COUNT;
    inserted_rows := inserted_rows + cur_rows;

    -- Free temp objects early
    DROP TABLE IF EXISTS _dedup;

    -- Advance
    v_start := v_end + 1;
  END LOOP;

  -- Recreate helper index(es) AFTER load
  CREATE INDEX IF NOT EXISTS idx_price_date ON pricing.price_observation(ts_date DESC);

  -- If you want to guarantee uniqueness for future upserts:
  -- CREATE UNIQUE INDEX IF NOT EXISTS price_observation_uniq
  --   ON pricing.price_observation (print_id, source_id, metric_id, ts_date);
  ALTER TABLE pricing.price_observation RESET (autovacuum_enabled);
  ANALYZE pricing.price_observation;

  RAISE NOTICE 'Inserted % rows total.', inserted_rows;
END;
$$;
COMMIT;
----------The last step should be to add back the references


--
--script to add the products
--
CREATE OR REPLACE PROCEDURE pricing.product_migration_price(records JSONB)
LANGUAGE plpgsql
AS $$
DECLARE
    kv RECORD;
    v_print_id            BIGINT;
    v_scryfall_id         UUID;
    v_multiverse_id       BIGINT;
    v_tcg_id              BIGINT;
    v_source_id           pricing.price_source.source_id%TYPE;
    v_card_game_id        card_catalog.card_games_ref.game_id%TYPE;
    v_game_id             card_catalog.games_ref.game_id%TYPE;
    v_card_version_id     UUID;
    v_product_id          pricing.product_ref.product_id%TYPE;
    v_created_product_id  pricing.product_ref.product_id%TYPE;
    v_source_product_id   pricing.source_product.source_product_id%TYPE;
    v_rows_updated        INT := 0;
    v_last_update_count   INT := 0;
    v_missing_count       INT := 0;
    v_total_records       INT := 0;
BEGIN
    -- Create temp table to track missing IDs
    CREATE TEMP TABLE temp_missing_ids (
        print_id BIGINT,
        scryfall_id UUID,
        multiverse_id BIGINT,
        tcg_id BIGINT,
        error_reason TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    ) ON COMMIT PRESERVE ROWS;

    --decompress chunks if needed (uncomment if you need to decompress chunks to update the data, but be careful with large datasets)
    SELECT decompress_chunk(i, if_compressed => true) 
    FROM show_chunks('pricing.price_observation') i;

    -- Fetch source_id once
    SELECT ps.source_id INTO v_source_id
    FROM pricing.price_source ps
    WHERE ps.code = 'mtgstocks';

    -- Fetch game IDs
    SELECT game_id INTO v_card_game_id
    FROM card_catalog.card_games_ref
    WHERE code = 'mtg';

    SELECT game_id INTO v_game_id
    FROM card_catalog.games_ref
    WHERE game_description = 'paper';

    IF v_source_id IS NULL THEN
        RAISE EXCEPTION 'price_source with code=% not found', 'mtgstocks';
    END IF;

    -- Iterate dict: key=print_id, value={...}
    FOR kv IN
        SELECT key, value
        FROM jsonb_each(records)
    LOOP
        v_total_records := v_total_records + 1;
        
        BEGIN
            -- Parse print_id from key
            v_print_id := kv.key::BIGINT;

            -- Parse identifiers from value object
            v_scryfall_id   := NULLIF(kv.value->>'scryfall_id', '')::UUID;
            v_multiverse_id := NULLIF(kv.value->>'multiverse_id', '')::BIGINT;
            v_tcg_id        := NULLIF(kv.value->>'tcg_id', '')::BIGINT;

            v_card_version_id := NULL;

            -- Resolve card_version_id (priority: scryfall -> tcg -> multiverse)
            IF v_scryfall_id IS NOT NULL THEN
                SELECT cei.card_version_id INTO v_card_version_id
                FROM card_catalog.card_external_identifier cei
                JOIN card_catalog.card_identifier_ref cir
                  ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                WHERE cir.identifier_name = 'scryfall_id'
                  AND cei.value = v_scryfall_id::text
                LIMIT 1;
            END IF;

            IF v_card_version_id IS NULL AND v_tcg_id IS NOT NULL THEN
                SELECT cei.card_version_id INTO v_card_version_id
                FROM card_catalog.card_external_identifier cei
                JOIN card_catalog.card_identifier_ref cir
                  ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                WHERE cir.identifier_name = 'tcgplayer_id'
                  AND cei.value = v_tcg_id::text
                LIMIT 1;
            END IF;

            IF v_card_version_id IS NULL AND v_multiverse_id IS NOT NULL THEN
                SELECT cei.card_version_id INTO v_card_version_id
                FROM card_catalog.card_external_identifier cei
                JOIN card_catalog.card_identifier_ref cir
                  ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                WHERE cir.identifier_name = 'multiverse_id'
                  AND cei.value = v_multiverse_id::text
                LIMIT 1;
            END IF;

            -- If card_version_id not found, log and continue
            IF v_card_version_id IS NULL THEN
                INSERT INTO temp_missing_ids (print_id, scryfall_id, multiverse_id, tcg_id, error_reason)
                VALUES (v_print_id, v_scryfall_id, v_multiverse_id, v_tcg_id, 
                        'No card_version_id found for any identifier');
                v_missing_count := v_missing_count + 1;
                CONTINUE;  -- Skip to next record
            END IF;

            -- Get or create product_id for this card_version_id
            v_product_id := NULL;
            SELECT mcp.product_id INTO v_product_id
            FROM pricing.mtg_card_products mcp
            WHERE mcp.card_version_id = v_card_version_id
            LIMIT 1;

            IF v_product_id IS NULL THEN
                -- Create product_ref
                INSERT INTO pricing.product_ref (game_id)
                VALUES (v_game_id)
                RETURNING product_id INTO v_created_product_id;

                -- Try to link card_version -> product
                INSERT INTO pricing.mtg_card_products (product_id, game_version_id, card_version_id)
                VALUES (v_created_product_id, v_game_id, v_card_version_id)
                ON CONFLICT (card_version_id) DO NOTHING;

                -- Reuse existing product_id if conflict
                SELECT mcp.product_id INTO v_product_id
                FROM pricing.mtg_card_products mcp
                WHERE mcp.card_version_id = v_card_version_id
                LIMIT 1;

                -- Cleanup orphan if needed
                IF v_product_id IS DISTINCT FROM v_created_product_id THEN
                    DELETE FROM pricing.product_ref pr
                    WHERE pr.product_id = v_created_product_id
                      AND NOT EXISTS (SELECT 1 FROM pricing.mtg_card_products m WHERE m.product_id = v_created_product_id)
                      AND NOT EXISTS (SELECT 1 FROM pricing.source_product sp WHERE sp.product_id = v_created_product_id);
                END IF;
            END IF;

            IF v_product_id IS NULL THEN
                INSERT INTO temp_missing_ids (print_id, scryfall_id, multiverse_id, tcg_id, error_reason)
                VALUES (v_print_id, v_scryfall_id, v_multiverse_id, v_tcg_id, 
                        'Failed to create/resolve product_id');
                v_missing_count := v_missing_count + 1;
                CONTINUE;
            END IF;

            -- Upsert source_product
            INSERT INTO pricing.source_product (product_id, source_id)
            VALUES (v_product_id, v_source_id)
            ON CONFLICT (product_id, source_id)
            DO UPDATE SET product_id = EXCLUDED.product_id
            RETURNING source_product_id INTO v_source_product_id;

            -- Update price_observation
            UPDATE pricing.price_observation po
            SET source_product_id = v_source_product_id
            WHERE po.print_id = v_print_id
              AND po.source_id = v_source_id;

            GET DIAGNOSTICS v_last_update_count = ROW_COUNT;
            v_rows_updated := v_rows_updated + v_last_update_count;

        SELECT compress_chunk(i) 
        FROM show_chunks('pricing.price_observation', 'oldest');
        
        EXCEPTION WHEN OTHERS THEN
            -- Catch any other errors and log them
            INSERT INTO temp_missing_ids (print_id, scryfall_id, multiverse_id, tcg_id, error_reason)
            VALUES (v_print_id, v_scryfall_id, v_multiverse_id, v_tcg_id, 
                    'Exception: ' || SQLERRM);
            v_missing_count := v_missing_count + 1;
            CONTINUE;
        END;

    END LOOP;

    -- Final report
    RAISE NOTICE 'Migration Summary: Total=%, Updated=%, Missing/Failed=%',
        v_total_records, v_rows_updated, v_missing_count;

    -- Show missing IDs if any
    IF v_missing_count > 0 THEN
        RAISE NOTICE 'Missing IDs stored in temp_missing_ids table. Query with: SELECT * FROM temp_missing_ids;';
    END IF;

END;
$$;



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

  -- 4) insert into stg_price_observation
  INSERT INTO pricing.stg_price_observation (
    game_code, print_id, metric_code, is_foil, source_code, value,
    product_id, source_product_id, scraped_at
  )
  SELECT
    r.game_code,
    r.print_id,
    r.metric_code,
    r.is_foil,
    r.source_code,
    r.value,
    mcp.product_id::text,
    sp.source_product_id,
    r.scraped_at
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
  WHERE r.card_version_id IS NOT NULL;

  GET DIAGNOSTICS v_inserted = ROW_COUNT;

  -- 5) mark rejects as resolved (for those we resolved)
  UPDATE pricing.stg_price_observation_reject rej
  SET
    resolved_at = now(),
    resolved_card_version_id = r.card_version_id,
    resolved_method = r.resolution_method,
    resolved_product_id = mcp.product_id,
    resolved_source_product_id = sp.source_product_id,
    is_terminal = TRUE,
    terminal_reason = 'Resolved via ' || r.resolution_method || ' mapping'
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
  WHERE rej.ts_date = r.ts_date
    AND rej.print_id = r.print_id
    AND rej.metric_code = r.metric_code
    AND rej.is_foil = r.is_foil
    AND rej.source_code = r.source_code
    AND rej.scraped_at = r.scraped_at
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