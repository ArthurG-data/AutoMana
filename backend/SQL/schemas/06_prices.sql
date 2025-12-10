CREATE SCHEMA IF NOT EXISTS pricing;
CREATE TABLE IF NOT EXISTS price_source (
  source_id   SMALLSERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'tcgplayer','cardkingdom','ebay','amazon', etc.
  name       TEXT NOT NULL,
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
    print_id      BIGINT      NOT NULL,
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
print_id      BIGINT      NOT NULL,
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
  print_id      BIGINT      NOT NULL,
  source_id     SMALLINT    NOT NULL,-- REFERENCES price_source(source_id),
  metric_id     SMALLINT    NOT NULL,-- REFERENCES price_metric(metric_id),
  --condition_id  SMALLINT    NOT NULL,-- REFERENCES price_condition(condition_id) DEFAULT  (SELECT condition_id FROM price_condition WHERE code='U'),
  value         NUMERIC(12,4) NOT NULL,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS price_observation;
CREATE TABLE IF NOT EXISTS price_observation (
  ts_date       DATE        NOT NULL,
  game_id      SMALLINT    NOT NULL REFERENCES card_game(game_id),
  print_id      BIGINT      NOT NULL,
  source_id     SMALLINT    NOT NULL  REFERENCES price_source(source_id),
  metric_id     SMALLINT    NOT NULL  REFERENCES price_metric(metric_id),
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  value         NUMERIC(12,4) NOT NULL,
  PRIMARY KEY (print_id, source_id, metric_id, ts_date)
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


--translate code to id
CREATE OR REPLACE PROCEDURE load_staging_prices_batched(batch_days int DEFAULT 30)
LANGUAGE plpgsql
AS $$
DECLARE
  v_min date;
  v_max date;
  v_start date;
  v_end   date;
  cur_rows bigint;
  total_inserted bigint := 0;
BEGIN
  -- determine overall date range from raw data
  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM raw_mtg_stock_price;
  IF v_min IS NULL THEN
    RAISE NOTICE 'load_staging_prices_batched: no rows in raw_mtg_stock_price';
    RETURN;
  END IF;

  v_start := v_min;
  WHILE v_start <= v_max LOOP
    v_end := LEAST(v_start + (batch_days - 1), v_max);

    RAISE NOTICE 'Loading raw -> staging for % to %', v_start, v_end;

    INSERT INTO stg_price_observation (
      ts_date, game_code, print_id, source_code, metric_code, value, scraped_at
    )
    SELECT
      s.ts_date,
      s.game_code,
      s.print_id,
      s.source_code,
      v.metric_code,
      v.value,
      s.scraped_at
    FROM raw_mtg_stock_price s
    CROSS JOIN LATERAL (VALUES
        ('price_low',         s.price_low),
        ('price_avg',         s.price_avg),
        ('price_foil',        s.price_foil),
        ('price_market',      s.price_market),
        ('price_market_foil', s.price_market_foil)
    ) AS v(metric_code, value)
    WHERE s.ts_date >= v_start AND s.ts_date <= v_end
      AND v.value IS NOT NULL;

    GET DIAGNOSTICS cur_rows = ROW_COUNT;
    total_inserted := total_inserted + cur_rows;
    RAISE NOTICE 'Inserted % rows for batch', cur_rows;

    -- advance to next batch
    v_start := v_end + 1;
  END LOOP;

  RAISE NOTICE 'load_staging_prices_batched: total inserted % rows', total_inserted;
END;
$$;
  
CREATE OR REPLACE PROCEDURE load_dim_from_staging()
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE NOTICE 'Loading dimension from staging...';

  INSERT INTO dim_price_observation (
    ts_date, game_id, print_id, source_id, metric_id,
    value, scraped_at
  )
  SELECT
    s.ts_date,
    cg.game_id,
    s.print_id,
    ps.source_id,
    pm.metric_id,
    s.value,
    s.scraped_at
  FROM stg_price_observation s
  JOIN card_game       cg ON cg.code = s.game_code
  JOIN price_source    ps ON ps.code = s.source_code
  JOIN price_metric pm ON pm.code = s.metric_code
  WHERE s.value IS NOT NULL;

  CREATE INDEX IF NOT EXISTS dim_price_obs_ts_idx
  ON dim_price_observation (ts_date);
END;
$$;

CREATE OR REPLACE PROCEDURE load_prices_from_dim_batched(batch_days int DEFAULT 30)
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

  -- Nothing to do?
  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM dim_price_observation;
  IF v_min IS NULL THEN
    RAISE NOTICE 'No rows in dim_price_observation.';
    RETURN;
  END IF;

  -- Reduce write-time overhead on target
  DROP INDEX IF EXISTS public.idx_price_date;
  ALTER TABLE price_observation SET (autovacuum_enabled = off);

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
      FROM dim_price_observation d
      WHERE d.ts_date >= v_start AND d.ts_date <= v_end
    ) x
    WHERE rn = 1;

    CREATE INDEX ON _dedup (ts_date);

    -- Insert in time order to keep inserts chunk-local
    INSERT INTO price_observation (ts_date, game_id, print_id, source_id, metric_id, value, scraped_at)
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
  CREATE INDEX IF NOT EXISTS idx_price_date ON price_observation(ts_date DESC);

  -- If you want to guarantee uniqueness for future upserts:
  -- CREATE UNIQUE INDEX IF NOT EXISTS price_observation_uniq
  --   ON price_observation (print_id, source_id, metric_id, ts_date);

  ALTER TABLE price_observation RESET (autovacuum_enabled);
  ANALYZE price_observation;

  RAISE NOTICE 'Inserted % rows total.', inserted_rows;
END;
$$;

----------The last step should be to add back the references

-