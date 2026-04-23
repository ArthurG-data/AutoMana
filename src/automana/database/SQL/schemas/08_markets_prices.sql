BEGIN;

CREATE SCHEMA IF NOT EXISTS markets;

-- TimescaleDB is required for `create_hypertable` + continuous aggregates
-- below. The extension is installed once in 01_set_schema.sql; this is a
-- belt-and-suspenders guard for direct-file runs.
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ============================================================
-- Function defined early so the triggers at the bottom can wire to
-- it by name. Schema-qualified so it lands in `markets` regardless
-- of the caller's search_path.
-- ============================================================

CREATE OR REPLACE FUNCTION markets.trigger_set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS markets.market_ref (
    market_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    country_code VARCHAR(3) NOT NULL DEFAULT 'AUD',
    city VARCHAR(20) NOT NULL DEFAULT 'Unknown',
    api_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (name, city, country_code)
);

CREATE TABLE IF NOT EXISTS markets.product_ref (
    product_shop_id VARCHAR(64) PRIMARY KEY,
    product_id TEXT NOT NULL,
    market_id INT NOT NULL REFERENCES markets.market_ref(market_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (market_id, product_id)
);

CREATE TABLE IF NOT EXISTS markets.card_products_ref (
    tcgplayer_id INT NOT NULL,
    product_shop_id VARCHAR(64) NOT NULL REFERENCES markets.product_ref(product_shop_id) ON DELETE CASCADE,
    description TEXT,
    quantity INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tcgplayer_id, product_shop_id)
);

CREATE TABLE IF NOT EXISTS markets.product_prices (
    time TIMESTAMPTZ NOT NULL,
    product_shop_id VARCHAR(64) NOT NULL REFERENCES markets.product_ref(product_shop_id) ON DELETE CASCADE,
    price NUMERIC NOT NULL,
    currency VARCHAR(3) NOT NULL,
    price_usd NUMERIC NOT NULL,
    source TEXT,
    is_foil BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (time, product_shop_id, is_foil)
);

CREATE TABLE IF NOT EXISTS markets.collection_handles (
    handle_id SERIAL PRIMARY KEY,
    market_id INT NOT NULL REFERENCES markets.market_ref(market_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (market_id, name)
);

-- handles_theme.theme_id references the canonical card-game table in
-- the `pricing` schema (`pricing.card_game`, defined in 06_prices.sql).
-- Previously this was an unqualified FK to `card_game` which could not
-- resolve at replay time.
CREATE TABLE IF NOT EXISTS markets.handles_theme (
    handle_id INT NOT NULL REFERENCES markets.collection_handles(handle_id) ON DELETE CASCADE,
    theme_id SMALLINT REFERENCES pricing.card_game(game_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (handle_id, theme_id)
);


-- ============================================================
-- Trigger functions
-- ============================================================

-- Soft-delete rows in markets.handles_theme when their pricing.card_game
-- parent is deleted. Fires before DELETE so we update the child before
-- ON DELETE SET NULL would otherwise nil the FK.
CREATE OR REPLACE FUNCTION markets.soft_delete_handles_theme()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE markets.handles_theme
    SET is_active = FALSE
    WHERE theme_id = OLD.game_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_product_prices_shop_time
    ON markets.product_prices (product_shop_id, time DESC);


-- ============================================================
-- Triggers
-- ============================================================

DROP TRIGGER IF EXISTS collection_handles_set_updated_at ON markets.collection_handles;
CREATE TRIGGER collection_handles_set_updated_at
BEFORE UPDATE ON markets.collection_handles
FOR EACH ROW
EXECUTE FUNCTION markets.trigger_set_updated_at();

-- Removed: trigger BEFORE UPDATE ON theme_ref — that table does not exist
-- anywhere in the schema. It was dead code tied to a historical design.

DROP TRIGGER IF EXISTS soft_delete_handles_theme_trigger ON pricing.card_game;
CREATE TRIGGER soft_delete_handles_theme_trigger
BEFORE DELETE ON pricing.card_game
FOR EACH ROW
EXECUTE FUNCTION markets.soft_delete_handles_theme();


-- ============================================================
-- TimescaleDB: hypertable, compression policy, continuous aggregate
-- ============================================================

SELECT create_hypertable(
    'markets.product_prices',
    'time',
    chunk_time_interval => interval '7 days',
    if_not_exists => TRUE
);

ALTER TABLE markets.product_prices
SET (timescaledb.compress, timescaledb.compress_segmentby = 'product_shop_id');

SELECT add_compression_policy('markets.product_prices', INTERVAL '30 days', if_not_exists => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS markets.card_price_daily_avg
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS day,
       product_shop_id,
       AVG(price) AS avg_price
FROM markets.product_prices
GROUP BY day, product_shop_id
WITH NO DATA;


-- ============================================================
-- Stored procedures
-- ============================================================

CREATE OR REPLACE PROCEDURE markets.add_price_batch_arrays(
    p_times            timestamptz[],
    p_product_shop_ids text[],
    p_prices           numeric[],
    p_currencies       text[],
    p_prices_usd       numeric[],
    p_is_foil          boolean[],
    p_sources          text[]
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO markets.product_prices
        (time, product_shop_id, price, currency, price_usd, is_foil, source)
    SELECT b.time, b.product_shop_id, b.price, b.currency, b.price_usd, b.is_foil, b.source
    FROM unnest(
            p_times, p_product_shop_ids, p_prices, p_currencies,
            p_prices_usd, p_is_foil, p_sources
         ) AS b(time, product_shop_id, price, currency, price_usd, is_foil, source)
    ON CONFLICT (time, product_shop_id, is_foil) DO NOTHING;
END;
$$;

CREATE OR REPLACE PROCEDURE markets.add_product_batch_arrays(
    p_product_shop_ids text[],
    p_product_ids      text[],
    p_market_ids       int[],
    p_created_at       timestamptz[],
    p_updated_at       timestamptz[]
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO markets.product_ref
        (product_shop_id, product_id, market_id, created_at, updated_at)
    SELECT b.product_shop_id, b.product_id, b.market_id, b.created_at, b.updated_at
    FROM unnest(
            p_product_shop_ids, p_product_ids, p_market_ids,
            p_created_at, p_updated_at
         ) AS b(product_shop_id, product_id, market_id, created_at, updated_at)
    ON CONFLICT (product_shop_id) DO NOTHING;
END;
$$;

CREATE OR REPLACE PROCEDURE markets.add_card_product_ref_batch(
    p_tcgplayer_ids    INT[],
    p_product_shop_ids TEXT[],
    p_created_ats      TIMESTAMPTZ[],
    p_updated_ats      TIMESTAMPTZ[]
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO markets.card_products_ref
        (tcgplayer_id, product_shop_id, created_at, updated_at)
    SELECT b.tcgplayer_id, b.product_shop_id, b.created_at, b.updated_at
    FROM unnest(
            p_tcgplayer_ids, p_product_shop_ids,
            p_created_ats, p_updated_ats
         ) AS b(tcgplayer_id, product_shop_id, created_at, updated_at)
    ON CONFLICT (tcgplayer_id, product_shop_id) DO NOTHING;
END;
$$;

COMMIT;
