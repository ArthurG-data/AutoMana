CREATE TABLE IF NOT EXISTS price_source (
  source_id   SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'mtgstocks','tcgplayer','scryfall','cardmarket','ebay'
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE price_metric (
  metric_id   SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'low','avg','high','market','list','sold','median'
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_condition (
  condition_id SMALLSERIAL PRIMARY KEY,
  code         TEXT UNIQUE default 'NM',  -- 'NM','LP','MP','HP','U' (unknown), 'D'
  description  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE card_finished(
    finish_id   SMALLSERIAL PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,   -- 'nonfoil','foil','etched','gilded'
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_game (
  game_id     SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'mtg','yugioh','pokemon', etc.
  name       TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- create hypertable
SELECT create_hypertable('price_observation',
                         by_range('ts_date'),
                         if_not_exists => TRUE);

-- Add a space (hash) dimension on print_id for parallelism & chunk fan-out:
SELECT add_dimension('price_observation', 'print_id', number_partitions => 8);

--set chunk time
SELECT set_chunk_time_interval('price_observation', INTERVAL '90 days');

CREATE INDEX IF NOT EXISTS idx_price_date ON price_observation(ts_date DESC);


ALTER TABLE price_observation
  SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'card_version_id',
       timescaledb.compress_orderby   = 'ts_date DESC');

-- Auto-compress anything older than 180 days:
SELECT add_compression_policy('mtg_price', INTERVAL '180 days');

CREATE MATERIALIZED VIEW price_weekly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 week', ts_date) AS week,
       print_id,
       AVG(price_low)  AS price_low,
       AVG(price_avg)  AS price_avg,
       AVG(price_high) AS price_high,
       AVG(price_foil) AS price_foil
FROM mtg_price
GROUP BY week, print_id;

SELECT add_continuous_aggregate_policy('price_weekly',
  start_offset => INTERVAL '365 days',
  end_offset   => INTERVAL '1 day',
  schedule_interval => INTERVAL '1 hour')

----------------------------Staging process

--grab the game_id
CREATE FUNCTION OR REPLACE insert
WITH 
    select gameid AS (
        SELECT game_id 
        FROM card_game 
        WHERE code = 
    )


DROP TABLE IF EXISTS raw_mtg_stock_price;
CREATE UNLOGGED TABLE raw_mtg_stock_price(
    ts_date       DATE        NOT NULL,
    game_code     TEXT       NOT NULL, --REFERENCES card_game(game_id),
    card_version_id      UUID      NOT NULL,
    price_low     NUMERIC(12,4),
    price_avg     NUMERIC(12,4),
    price_foil   NUMERIC(12,4),
    price_market NUMERIC(12,4),
    price_market_foil NUMERIC(12,4),
    source_code     TEXT    NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS stg_price_observation;
CREATE UNLOGGED TABLE stg_price_observation (
ts_date       DATE        NOT NULL,
game_code     TEXT       NOT NULL, --REFERENCES card_game(game_id),
card_version_id      UUID      NOT NULL,
metric_code     TEXT    NOT NULL,-- REFERENCES price_metric(metric_id),
source_code     TEXT    NOT NULL,-- REFERENCES price_source(source_id),
--condition_code  TEXT    NOT NULL,-- REFERENCES price_condition(condition_id) DEFAULT  (SELECT condition_id FROM price_condition WHERE code='U'),
value         NUMERIC(12,4) NOT NULL,
scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS dim_price_observation;
CREATE UNLOGGED TABLE IF NOT EXISTS dim_price_observation (
  ts_date       DATE        NOT NULL,
  game_id      SMALLINT    NOT NULL, --REFERENCES card_game(game_id),
  card_version_id      UUID      NOT NULL,
  source_id     SMALLINT    NOT NULL,-- REFERENCES price_source(source_id),
  metric_id     SMALLINT    NOT NULL,-- REFERENCES price_metric(metric_id),
  --condition_id  SMALLINT    NOT NULL,-- REFERENCES price_condition(condition_id) DEFAULT  (SELECT condition_id FROM price_condition WHERE code='U'),
  value         NUMERIC(12,4) NOT NULL,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS price_observation;
CREATE TABLE IF NOT EXISTS price_observation (
  ts_date       DATE        NOT NULL,
  game_id      SMALLINT    NOT NULL, --REFERENCES card_game(game_id),
  card_version_id      UUID      NOT NULL,
  source_id     SMALLINT    NOT NULL,-- REFERENCES price_source(source_id),
  metric_id     SMALLINT    NOT NULL,-- REFERENCES price_metric(metric_id),
  --condition_id  SMALLINT    NOT NULL,-- REFERENCES price_condition(condition_id) DEFAULT  (SELECT condition_id FROM price_condition WHERE code='U'),
  value         NUMERIC(12,4) NOT NULL,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (card_version_id, source_id, metric_id, ts_date)
);

-- create hypertable
SELECT create_hypertable('price_observation',
                         by_range('ts_date'),
                         if_not_exists => TRUE);

-- Add a space (hash) dimension on card_version_id for parallelism & chunk fan-out:
SELECT add_dimension('price_observation', 'card_version_id', number_partitions => 8);

--set chunk time
SELECT set_chunk_time_interval('price_observation', INTERVAL '90 days');

CREATE INDEX IF NOT EXISTS idx_price_date ON price_observation(ts_date DESC);


--translate code to id
CREATE OR REPLACE PROCEDURE load_staging_prices()
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO stg_price_observation (
    ts_date, game_code, card_version_id, source_code,
    metric_code, 
   value, scraped_at
  )
  SELECT
    s.ts_date,
    s.game_code,
    s.card_version_id,
    s.source_code,
    v.metric_code,
    --COALESCE(s.condition_code, 'U') AS condition_code,
    v.value,                   -- pass-through for now, or convert to USD
    s.scraped_at
  FROM raw_mtg_stock_price s
  CROSS JOIN LATERAL (
    VALUES
      ('price_low',        s.price_low),
      ('price_avg',        s.price_avg),
      ('price_foil',       s.price_foil),
      ('price_market',     s.price_market),
      ('price_market_foil',s.price_market_foil)
  ) AS v(metric_code, value)
  WHERE v.value IS NOT NULL;

  TRUNCATE TABLE str_mtg_stock_price;
END;
$$;

CREATE OR REPLACE PROCEDURE load_dim_from_staging()
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO dim_price_observation (
    ts_date, game_id, card_version_id, source_id, metric_id,
    value, scraped_at
  )
  SELECT
    s.ts_date,
    cg.game_id,
    s.card_version_id,
    ps.source_id,
    pm.metric_id,
    s.value,
    s.scraped_at
  FROM stg_price_observation s
  JOIN card_game       cg ON cg.code = s.game_code
  JOIN price_source    ps ON ps.code = s.source_code
  JOIN price_metric pm ON pm.code = s.metric_code
  WHERE s.value IS NOT NULL;

  TRUNCATE TABLE stg_price_observation;
END;
$$;

CREATE OR REPLACE PROCEDURE load_prices_from_dim()
LANGUAGE plpgsql
AS $$
DECLARE
  total_rows bigint;
  inserted_rows bigint;
BEGIN
  -- quick guard
  SELECT count(*) INTO total_rows FROM dim_price_observation;
  IF total_rows = 0 THEN
    RAISE NOTICE 'load_prices_from_dim: no rows to import';
    RETURN;
  END IF;

  /*
    Deduplicate rows in dim_price_observation by key (card_version_id, source_id, metric_id, ts_date)
    taking the most recent scraped_at value per key. This enforces a single "unique" row per key
    before inserting/upserting into the concrete hypertable.
  */
  WITH dedup AS (
    SELECT DISTINCT ON (card_version_id, source_id, metric_id, ts_date)
      ts_date,
      game_id,
      card_version_id,
      source_id,
      metric_id,
      value,
      scraped_at
    FROM dim_price_observation
    ORDER BY card_version_id, source_id, metric_id, ts_date, scraped_at DESC
  )
  INSERT INTO price_observation (
    ts_date,
    game_id,
    card_version_id,
    source_id,
    metric_id,
    value,
    scraped_at
  )
  SELECT
    d.ts_date,
    d.game_id,
    d.card_version_id,
    d.source_id,
    d.metric_id,
    d.value,
    d.scraped_at
  FROM dedup d
  --JOIN card_version cv ON cv.card_version_id = d.card_version_id
  -- upsert to ensure uniqueness in the final table (adjust conflict target to match your PK)
  ON CONFLICT (card_version_id, source_id, metric_id, ts_date)
    DO UPDATE SET
      value = EXCLUDED.value,
      scraped_at = EXCLUDED.scraped_at;

  GET DIAGNOSTICS inserted_rows = ROW_COUNT;
  RAISE NOTICE 'load_prices_from_dim: imported % distinct rows from % source rows', inserted_rows, total_rows;

  TRUNCATE TABLE dim_price_observation;
END;
$$;

----------The last step should be to add back the references