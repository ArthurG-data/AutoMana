CREATE TABLE price_source (
  source_id   SMALLINT PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'mtgstocks','tcgplayer','scryfall','cardmarket','ebay'
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE price_metric (
  metric_id   SMALLINT PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'low','avg','high','market','list','sold','median'
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE price_condition (
  condition_id SMALLINT PRIMARY KEY,
  code         TEXT UNIQUE NOT NULL,  -- 'NM','LP','MP','HP','U' (unknown)
  description  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE card_finished(
    finish_id   SMALLINT PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,   -- 'nonfoil','foil','etched','gilded'
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_game (
  game_id     SMALLINT PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,   -- 'mtg','yugioh','pokemon', etc.
  name       TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE price_observation (
  ts_date       DATE        NOT NULL,
  game_id      SMALLINT    NOT NULL, --REFERENCES card_game(game_id),
  print_id      BIGINT      NOT NULL,
  source_id     SMALLINT    NOT NULL,-- REFERENCES price_source(source_id),
  metric_id     SMALLINT    NOT NULL,-- REFERENCES price_metric(metric_id),
  condition_id  SMALLINT    NOT NULL,-- REFERENCES price_condition(condition_id) DEFAULT  (SELECT condition_id FROM price_condition WHERE code='U'),
  finish_id     SMALLINT    NOT NULL,-- REFERENCES card_finished(finish_id) DEFAULT  (SELECT finish_id FROM card_finished WHERE code='nonfoil'),
  currency      CHAR(3)     NOT NULL,   -- e.g., 'USD','EUR','AUD'
  value         NUMERIC(12,4) NOT NULL,
  usd_value     NUMERIC(12,4) NOT NULL,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (print_id, source_id, metric_id, finish_id, condition_id, currency, ts_date)
);

SELECT create_hypertable('price_observation',
                         by_range('ts_date'),
                         if_not_exists => TRUE);

-- Add a space (hash) dimension on print_id for parallelism & chunk fan-out:
SELECT add_dimension('price_observation', 'print_id', number_partitions => 8);

SELECT set_chunk_time_interval('price_observation', INTERVAL '90 days');

CREATE INDEX IF NOT EXISTS idx_price_date ON price_observation(ts_date DESC);


ALTER TABLE price_observation
  SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'print_id',
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


DROP TABLE IF EXISTS str_mtg_stock_price;
CREATE UNLOGGED TABLE str_mtg_stock_price(
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
price_low     NUMERIC(12,4),
price_avg     NUMERIC(12,4),
price_foil   NUMERIC(12,4),
price_market NUMERIC(12,4),
price_market_foil NUMERIC(12,4),
source_code     TEXT    NOT NULL,-- REFERENCES price_source(source_id),
metric_code     TEXT    NOT NULL,-- REFERENCES price_metric(metric_id),
condition_code  TEXT    NOT NULL,-- REFERENCES price_condition(condition_id) DEFAULT  (SELECT condition_id FROM price_condition WHERE code='U'),
finish_code     TEXT    NOT NULL,-- REFERENCES card_finished(finish_id) DEFAULT  (SELECT finish_id FROM card_finished WHERE code='nonfoil'),
currency      CHAR(3)     NOT NULL,   -- e.g., 'USD','EUR','AUD'
value         NUMERIC(12,4) NOT NULL,
usd_value     NUMERIC(12,4) NOT NULL,
scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)

--translate code to id