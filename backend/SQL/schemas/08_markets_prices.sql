CREATE SCHEMA IF NOT EXISTS markets;
SET search_path TO markets, public;

--- table-------------
CREATE TABLE markets.market_ref (
    market_id SERIAL PRIMARY KEY,  -- unique identifier for the market
    name TEXT NOT NULL UNIQUE,
    country_code VARCHAR(3) NOT NULL DEFAULT 'AUD',
    city VARCHAR(20) NOT NULL DEFAULT 'Unknown',                           -- e.g., ebay, tcgplayer, etc.
    api_url TEXT,                           -- optional: API endpoint for the market
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, city, country_code)
);

CREATE TABLE IF NOT EXISTS markets.product_ref(
    product_shop_id VARCHAR(64) PRIMARY KEY,  -- unique identifier for the product in the sho
    product_id TEXT NOT NULL,
    market_id INT NOT NULL REFERENCES market_ref(market_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (market_id, product_id)     -- ensure unique product per market
);

CREATE TABLE card_products_ref (
    tcgplayer_id INT NOT NULL,
    product_shop_id VARCHAR(64) NOT NULL REFERENCES product_ref(product_shop_id) ON DELETE CASCADE,
    description TEXT,  
    quantity INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tcgplayer_id, product_shop_id) -- ensure unique product per card and market, think about how conditions might be included,maybe modify the card table
);

CREATE TABLE product_prices (--producy prices, for cards at the moment but can be extended to other products
    time TIMESTAMPTZ NOT NULL,
    product_shop_id VARCHAR(64) NOT NULL REFERENCES product_ref(product_shop_id) ON DELETE CASCADE,
    price NUMERIC NOT NULL, 
    currency VARCHAR(3) NOT NULL,
    price_usd NUMERIC NOT NULL,      -- e.g., ebay, tcgplayer, etc.
    source TEXT,
    is_foil BOOLEAN DEFAULT FALSE                       , -- indicates if the price is for a foil version of the card
    PRIMARY KEY (time, product_shop_id, is_foil) -- composite primary key to allow multiple prices for the same product at different times and foil status
);


CREATE TABLE markets.collection_handles (
    handle_id SERIAL PRIMARY KEY,
    market_id INT  NOT NULL REFERENCES market_ref(market_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE( market_id, name)
);

CREATE TABLE markets.handles_theme(
  handle_id INT NOT NULL REFERENCES markets.collection_handles(handle_id) ON DELETE CASCADE,
  theme_id INT NOT NULL REFERENCES card_game(game_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY(handle_id, theme_id),
  is_active BOOLEAN DEFAULT TRUE
)
-- Create a trigger function to soft delete
CREATE OR REPLACE FUNCTION soft_delete_handles_theme()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE markets.handles_theme 
  SET is_active = FALSE 
  WHERE theme_id = OLD.game_id;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

----- indexes-------------
CREATE INDEX IF NOT EXISTS idx_porduct_price ON product_prices (product_shop_id, time DESC);


--------------------------Triggers
CREATE TRIGGER collection_handles_set_updated_at
BEFORE UPDATE ON collection_handles
FOR EACH ROW
EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER theme_set_updated_at
BEFORE UPDATE ON theme_ref
FOR EACH ROW
EXECUTE FUNCTION trigger_set_updated_at();

-- Create the trigger on the referenced table
CREATE TRIGGER soft_delete_handles_theme_trigger
    BEFORE DELETE ON card_game
    FOR EACH ROW
    EXECUTE FUNCTION soft_delete_handles_theme();

----------hyperytables 
SELECT create_hypertable('product_prices', 'time', chunk_time_interval => interval '7 days');
ALTER TABLE product_prices SET (timescaledb.compress, timescaledb.compress_segmentby = 'product_shop_id');
SELECT add_compression_policy('product_prices', INTERVAL '30 days');

CREATE MATERIALIZED VIEW card_price_daily_avg
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS day, product_shop_id, AVG(price) AS avg_price
FROM product_prices
GROUP BY day, product_shop_id;

--------------------views-------------------

--------------------Stored Procedures-------------------
CREATE OR REPLACE PROCEDURE add_price_batch_arrays(
  p_times            timestamptz[],
  p_product_shop_ids text[],
  p_prices           numeric[],
  p_currencies      text[],
  p_prices_usd      numeric[],
  p_is_foil			boolean[],
  p_sources          text[]
)
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO product_prices(time, product_shop_id, price,currency, price_usd, is_foil, source)
  SELECT b.time, b.product_shop_id, b.price, b.currency, b.price_usd, b.is_foil, b.source
  FROM unnest(
         p_times,
         p_product_shop_ids,
         p_prices,
         p_currencies,
         p_prices_usd,
		     p_is_foil,
         p_sources
       ) AS b(time, product_shop_id, price, currency, price_usd, is_foil, source)
    ON CONFLICT (time, product_shop_id, is_foil) DO NOTHING;
END;
$$;

CREATE OR REPLACE PROCEDURE add_product_batch_arrays(
  p_product_shop_ids           text[],
  p_product_ids             text[],
  p_market_ids           int[],
  p_created_at      timestamptz[],
  p_updated_at      timestamptz[]
)
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO product_ref(product_shop_id, product_id, market_id, created_at, updated_at)
  SELECT b.product_shop_id, b.product_id, b.market_id, b.created_at, b.updated_at
  FROM unnest(
            p_product_shop_ids,
            p_product_ids,
            p_market_ids,
            p_created_at,
            p_updated_at
       ) AS b(product_shop_id, product_id, market_id, created_at, updated_at)
    ON CONFLICT ( product_shop_id) DO NOTHING;
END;
$$;


CREATE OR REPLACE PROCEDURE add_card_product_ref_batch(
  p_tcgplayer_ids    INT[],
  p_product_shop_ids TEXT[],
  p_created_ats      TIMESTAMPTZ[],
  p_updated_ats      TIMESTAMPTZ[]
)
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO card_products_ref (
    tcgplayer_id,
    product_shop_id,
    created_at,
    updated_at
  )
  SELECT
    b.tcgplayer_id,
    b.product_shop_id,
    b.created_at,
    b.updated_at
  FROM unnest(
         p_tcgplayer_ids,
         p_product_shop_ids,
         p_created_ats,
         p_updated_ats
       ) AS b(
         tcgplayer_id,
         product_shop_id,
         created_at,
         updated_at
       )
  ON CONFLICT (tcgplayer_id, product_shop_id) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

