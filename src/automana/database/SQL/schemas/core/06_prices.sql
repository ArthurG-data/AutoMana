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
  ('GBP', 'British Pound'),
  ('AUD', 'Australian Dollar'),
  ('NZD', 'New Zealand Dollar'),
  ('TIX', 'Magic Online Tickets')
ON CONFLICT (currency_code) DO NOTHING;
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
  ('scryfall',  'Scryfall API'),
  ('ebay',      'eBay Fulfillment API — seller order history'),
  ('tcgtracking', 'Open TCG API — tcgtracking.com (TCGPlayer + Manapool aggregator)'),
  ('shopify',   'Shopify storefront price scrape')
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

-- card_catalog.card_finished is defined in 02_card_schema.sql (canonical finish reference).
-- Maps MTGStocks name suffixes (e.g. "Surge Foil") to their finish_id.
-- Used by load_staging_prices_batched, load_prices_from_staged_batched, and
-- resolve_price_rejects to assign granular finishes instead of generic FOIL.
CREATE TABLE IF NOT EXISTS pricing.mtgstock_name_finish_suffix (
    suffix     TEXT PRIMARY KEY,
    finish_id  SMALLINT NOT NULL REFERENCES card_catalog.card_finished(finish_id)
);

-- Maps MTGStocks "A"-prefixed art set codes to lowercase Scryfall equivalents.
CREATE TABLE IF NOT EXISTS pricing.mtgstock_art_set_map (
    mtgstocks_set_code  TEXT PRIMARY KEY,
    scryfall_set_code   TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Maps MTGStocks base set codes to Scryfall "t"-prefixed token set codes.
CREATE TABLE IF NOT EXISTS pricing.mtgstock_token_set_map (
    mtgstocks_set_code  TEXT PRIMARY KEY,
    token_set_code      TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Persistent PriceCharting product -> card_version match cache + provenance.
-- Populated by pricecharting.build_match_catalog; read by pricecharting.stage_sold.
-- See migration_62_pricecharting_card_map.sql for the full rationale.
CREATE TABLE IF NOT EXISTS pricing.pricecharting_card_map (
    pc_product_id    TEXT PRIMARY KEY,
    card_version_id  UUID REFERENCES card_catalog.card_version(card_version_id),
    set_code         TEXT,
    finish_id        SMALLINT,
    match_method     TEXT       NOT NULL DEFAULT 'none',
    certainty        SMALLINT   NOT NULL DEFAULT 0,
    tcg_vote_count   SMALLINT   NOT NULL DEFAULT 0,
    verified         BOOLEAN    NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pricecharting_card_map_cv
    ON pricing.pricecharting_card_map (card_version_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.pricecharting_card_map
    TO app_backend, app_celery;

INSERT INTO pricing.mtgstock_art_set_map (mtgstocks_set_code, scryfall_set_code) VALUES
    ('AAINR', 'ainr'),
    ('ADFT',  'adft'),
    ('AEOE',  'aeoe'),
    ('AFIN',  'afin'),
    ('AATDM', 'aatdm'),
    ('ASLD',  'asld'),
    ('APRE',  'apre'),
    ('AMAT',  'amat'),
    ('AACR',  'aacr'),
    ('AAFR',  'aafr'),
    ('ABLB',  'ablb'),
    ('ABRO',  'abro'),
    ('ACLB',  'aclb'),
    ('ACMM',  'acmm'),
    ('ADMU',  'admu'),
    ('ADSK',  'adsk'),
    ('AECL',  'aecl'),
    ('AFDN',  'afdn'),
    ('AJMP',  'ajmp'),
    ('AKHM',  'akhm'),
    ('ALCI',  'alci'),
    ('ALTC',  'altc'),
    ('ALTR',  'altr'),
    ('AMH1',  'amh1'),
    ('AMH2',  'amh2'),
    ('AMH3',  'amh3'),
    ('AMID',  'amid'),
    ('AMKM',  'amkm'),
    ('AMOM',  'amom'),
    ('ANEO',  'aneo'),
    ('AONE',  'aone'),
    ('AOTJ',  'aotj'),
    ('ASNC',  'asnc'),
    ('ASOS',  'asos'),
    ('ASPM',  'aspm'),
    ('ASTX',  'astx'),
    ('ATDM',  'atdm'),
    ('ATLA',  'atla'),
    ('ATLE',  'atle'),
    ('ATMT',  'atmt'),
    ('AVOW',  'avow'),
    ('AWOE',  'awoe'),
    ('AZNR',  'aznr')
ON CONFLICT (mtgstocks_set_code) DO NOTHING;

INSERT INTO pricing.mtgstock_token_set_map (mtgstocks_set_code, token_set_code) VALUES
    ('10E', 't10e'), ('2X2', 't2x2'), ('2XM', 't2xm'), ('30A', 't30a'),
    ('40K', 't40k'), ('A25', 'ta25'), ('ACR', 'tacr'), ('AER', 'taer'),
    ('AFC', 'tafc'), ('AFR', 'tafr'), ('AKH', 'takh'), ('ALA', 'tala'),
    ('ARB', 'tarb'), ('AVR', 'tavr'), ('BBD', 'tbbd'), ('BFZ', 'tbfz'),
    ('BIG', 'tbig'), ('BLB', 'tblb'), ('BLC', 'tblc'), ('BNG', 'tbng'),
    ('BOT', 'tbot'), ('BRC', 'tbrc'), ('BRO', 'tbro'), ('C14', 'tc14'),
    ('C15', 'tc15'), ('C16', 'tc16'), ('C17', 'tc17'), ('C18', 'tc18'),
    ('C19', 'tc19'), ('C20', 'tc20'), ('C21', 'tc21'), ('CLB', 'tclb'),
    ('CM2', 'tcm2'), ('CMA', 'tcma'), ('CMM', 'tcmm'), ('CMR', 'tcmr'),
    ('CN2', 'tcn2'), ('CNS', 'tcns'), ('CON', 'tcon'), ('DD1', 'tdd1'),
    ('DD2', 'tdd2'), ('DDC', 'tddc'), ('DDD', 'tddd'), ('DDE', 'tdde'),
    ('DDF', 'tddf'), ('DDG', 'tddg'), ('DDH', 'tddh'), ('DDI', 'tddi'),
    ('DDJ', 'tddj'), ('DDK', 'tddk'), ('DDL', 'tddl'), ('DDM', 'tddm'),
    ('DDS', 'tdds'), ('DDT', 'tddt'), ('DDU', 'tddu'), ('DFT', 'tdft'),
    ('DGM', 'tdgm'), ('DKA', 'tdka'), ('DMC', 'tdmc'), ('DMR', 'tdmr'),
    ('DMU', 'tdmu'), ('DOM', 'tdom'), ('DRC', 'tdrc'), ('DSC', 'tdsc'),
    ('DSK', 'tdsk'), ('DTK', 'tdtk'), ('DVD', 'tdvd'), ('E01', 'te01'),
    ('ECC', 'tecc'), ('ECL', 'tecl'), ('ELD', 'teld'), ('EMA', 'tema'),
    ('EMN', 'temn'), ('EOC', 'teoc'), ('EOE', 'teoe'), ('EVE', 'teve'),
    ('EVG', 'tevg'), ('FDN', 'tfdn'), ('FIC', 'tfic'), ('FIN', 'tfin'),
    ('FRF', 'tfrf'), ('GK1', 'tgk1'), ('GK2', 'tgk2'), ('GN2', 'tgn2'),
    ('GN3', 'tgn3'), ('GRN', 'tgrn'), ('GTC', 'tgtc'), ('GVL', 'tgvl'),
    ('HOB', 'thob'), ('HOU', 'thou'), ('IKO', 'tiko'), ('IMA', 'tima'),
    ('INR', 'tinr'), ('ISD', 'tisd'), ('JOU', 'tjou'), ('JVC', 'tjvc'),
    ('KHC', 'tkhc'), ('KHM', 'tkhm'), ('KLD', 'tkld'), ('KTK', 'tktk'),
    ('LCC', 'tlcc'), ('LCI', 'tlci'), ('LRW', 'tlrw'), ('LTC', 'tltc'),
    ('LTR', 'tltr'), ('M10', 'tm10'), ('M11', 'tm11'), ('M12', 'tm12'),
    ('M13', 'tm13'), ('M14', 'tm14'), ('M15', 'tm15'), ('M19', 'tm19'),
    ('M20', 'tm20'), ('M21', 'tm21'), ('M3C', 'tm3c'), ('MBS', 'tmbs'),
    ('MD1', 'tmd1'), ('MED', 'tmed'), ('MH1', 'tmh1'), ('MH2', 'tmh2'),
    ('MH3', 'tmh3'), ('MIC', 'tmic'), ('MID', 'tmid'), ('MKC', 'tmkc'),
    ('MKM', 'tmkm'), ('MM2', 'tmm2'), ('MM3', 'tmm3'), ('MMA', 'tmma'),
    ('MOC', 'tmoc'), ('MOM', 'tmom'), ('MOR', 'tmor'), ('MSH', 'tmsh'),
    ('MUL', 'tmul'), ('NCC', 'tncc'), ('NEC', 'tnec'), ('NEO', 'tneo'),
    ('NPH', 'tnph'), ('OGW', 'togw'), ('ONC', 'tonc'), ('ONE', 'tone'),
    ('ORI', 'tori'), ('OTC', 'totc'), ('OTJ', 'totj'), ('OTP', 'totp'),
    ('PCA', 'tpca'), ('PIP', 'tpip'), ('REX', 'trex'), ('RIX', 'trix'),
    ('RNA', 'trna'), ('ROE', 'troe'), ('RTR', 'trtr'), ('RVR', 'trvr'),
    ('SCD', 'tscd'), ('SHM', 'tshm'), ('SNC', 'tsnc'), ('SOC', 'tsoc'),
    ('SOI', 'tsoi'), ('SOM', 'tsom'), ('SOS', 'tsos'), ('SPM', 'tspm'),
    ('STX', 'tstx'), ('TDC', 'ttdc'), ('TDM', 'ttdm'), ('THB', 'tthb'),
    ('THS', 'tths'), ('TLA', 'ttla'), ('TLE', 'ttle'), ('TMC', 'ttmc'),
    ('TMT', 'ttmt'), ('TSR', 'ttsr'), ('UGL', 'tugl'), ('UMA', 'tuma'),
    ('UND', 'tund'), ('UNF', 'tunf'), ('UST', 'tust'), ('VOC', 'tvoc'),
    ('VOW', 'tvow'), ('WAR', 'twar'), ('WHO', 'twho'), ('WOC', 'twoc'),
    ('WOE', 'twoe'), ('WWK', 'twwk'), ('XLN', 'txln'), ('ZEN', 'tzen'),
    ('ZNC', 'tznc'), ('ZNR', 'tznr')
ON CONFLICT (mtgstocks_set_code) DO NOTHING;

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

INSERT INTO pricing.mtgstock_name_finish_suffix (suffix, finish_id) VALUES
  ('Surge Foil',    (SELECT finish_id FROM card_catalog.card_finished WHERE code = 'SURGE_FOIL')),
  ('Ripple Foil',   (SELECT finish_id FROM card_catalog.card_finished WHERE code = 'RIPPLE_FOIL')),
  ('Rainbow Foil',  (SELECT finish_id FROM card_catalog.card_finished WHERE code = 'RAINBOW_FOIL')),
  ('Foil Etched',   (SELECT finish_id FROM card_catalog.card_finished WHERE code = 'ETCHED')),
  ('Ripper Foil',   (SELECT finish_id FROM card_catalog.card_finished WHERE code = 'FOIL')),
  ('Textured Foil', (SELECT finish_id FROM card_catalog.card_finished WHERE code = 'FOIL'))
ON CONFLICT (suffix) DO NOTHING;

INSERT INTO pricing.price_source (code, name, currency_code) VALUES
  ('tcg', 'tcgplayer', 'USD'),
  ('cardkingdom', 'Card Kingdom', 'USD'),
  ('cardmarket', 'Cardmarket', 'EUR'),
  ('starcitygames', 'Star City Games', 'USD'),
  ('ebay', 'eBay', 'USD'),
  ('amazon', 'Amazon', 'USD'),
  ('mtgstocks', 'MTGStocks', 'USD'),
  ('cardhoarder', 'Cardhoarder', 'TIX'),
  ('manapool', 'manapool', 'USD'),
  ('cardsphere', 'cardsphere', 'USD'),
  ('gg_brisbane', 'Good Games Brisbane', 'AUD'),
  ('gg_sydney', 'Good Games Sydney', 'AUD'),
  ('pricecharting', 'PriceCharting', 'USD')
ON CONFLICT (code) DO NOTHING;
-------------------------------------------------------------------------------price observation table and staging tables for the ETL process
-- Finish default: NONFOIL
CREATE OR REPLACE FUNCTION pricing.default_finish_id()
RETURNS SMALLINT
LANGUAGE sql
STABLE
AS $$
  SELECT finish_id
  FROM card_catalog.card_finished
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
        REFERENCES card_catalog.card_finished(finish_id),
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
        REFERENCES card_catalog.card_finished(finish_id),
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
        REFERENCES card_catalog.card_finished(finish_id),
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

-------------------------------------------------------------------------------
--migration
-------------------------------------------------------------------------------
--from tier 1 to tier 2


--Tier 3: weekly aggre for older than 5 years
----------------------------Staging process
-- ===========================================================================
-- Materialized view: card price spark (added in migration_36)
--
-- Pre-computes per-card-version current price, 1d/7d/30d % changes, and a
-- 7-point sparkline for the standard TCGPlayer NM English Non-Foil market
-- (transaction_type_id=1, condition_id=1, language_id=1, finish_id=1).
-- Refreshed once per day via CALL pricing.refresh_card_price_spark().
-- ===========================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS pricing.mv_card_price_spark AS
WITH daily AS (
    SELECT
        ppd.card_version_id,
        ppd.price_date,
        -- Prefer NONFOIL (finish_id=1) list→sold, then fall back to any finish.
        -- This lets foil-only cards (headliners, serialized) appear in the spark
        -- instead of being silently excluded.
        COALESCE(
            AVG(ppd.list_avg_cents)  FILTER (WHERE ppd.finish_id = 1),
            AVG(ppd.sold_avg_cents)  FILTER (WHERE ppd.finish_id = 1),
            AVG(ppd.list_avg_cents),
            AVG(ppd.sold_avg_cents)
        ) / 100.0 AS avg_price
    FROM pricing.print_price_daily ppd
    WHERE ppd.transaction_type_id = 1
      AND ppd.condition_id        = 1
      AND ppd.language_id         = 1
      AND ppd.price_date          > CURRENT_DATE - 365  -- exclusive: mirrors original runtime query
    GROUP BY ppd.card_version_id, ppd.price_date
    HAVING COALESCE(
        AVG(ppd.list_avg_cents)  FILTER (WHERE ppd.finish_id = 1),
        AVG(ppd.sold_avg_cents)  FILTER (WHERE ppd.finish_id = 1),
        AVG(ppd.list_avg_cents),
        AVG(ppd.sold_avg_cents)
    ) IS NOT NULL
),
ranked AS (
    SELECT
        card_version_id,
        price_date,
        avg_price,
        ROW_NUMBER() OVER (PARTITION BY card_version_id ORDER BY price_date DESC) AS rn
    FROM daily
),
current_prices AS (
    SELECT card_version_id, price_date AS latest_price_date, avg_price AS current_price
    FROM ranked
    WHERE rn = 1
),
spark_rows AS (
    SELECT
        card_version_id,
        ARRAY_AGG(avg_price ORDER BY price_date ASC) AS spark
    FROM ranked
    WHERE rn <= 7
    GROUP BY card_version_id
)
SELECT
    cp.card_version_id,
    cp.current_price                                                              AS price,
    CASE
        WHEN d1.avg_price IS NULL OR d1.avg_price = 0 THEN 0.0
        ELSE ROUND(((cp.current_price - d1.avg_price) / d1.avg_price * 100)::numeric, 2)::float
    END                                                                           AS price_change_1d,
    CASE
        WHEN d7.avg_price IS NULL OR d7.avg_price = 0 THEN 0.0
        ELSE ROUND(((cp.current_price - d7.avg_price) / d7.avg_price * 100)::numeric, 2)::float
    END                                                                           AS price_change_7d,
    CASE
        WHEN d30.avg_price IS NULL OR d30.avg_price = 0 THEN 0.0
        ELSE ROUND(((cp.current_price - d30.avg_price) / d30.avg_price * 100)::numeric, 2)::float
    END                                                                           AS price_change_30d,
    COALESCE(sr.spark, ARRAY[cp.current_price])                                  AS spark
FROM current_prices cp
LEFT JOIN daily d1
    ON d1.card_version_id = cp.card_version_id
   AND d1.price_date      = cp.latest_price_date - INTERVAL '1 day'
LEFT JOIN daily d7
    ON d7.card_version_id = cp.card_version_id
   AND d7.price_date      = cp.latest_price_date - INTERVAL '7 days'
LEFT JOIN daily d30
    ON d30.card_version_id = cp.card_version_id
   AND d30.price_date      = cp.latest_price_date - INTERVAL '30 days'
LEFT JOIN spark_rows sr ON sr.card_version_id = cp.card_version_id
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_card_price_spark_cv
    ON pricing.mv_card_price_spark (card_version_id);

CREATE OR REPLACE PROCEDURE pricing.refresh_card_price_spark()
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pricing, pg_catalog
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY pricing.mv_card_price_spark;
    RAISE NOTICE 'pricing.mv_card_price_spark refreshed at %', now();
END;
$$;

GRANT EXECUTE ON PROCEDURE pricing.refresh_card_price_spark()
    TO app_celery, app_rw, app_admin;

GRANT SELECT ON pricing.mv_card_price_spark
    TO app_celery, app_rw, app_admin, app_ro;
-- ── eBay Scraped Sold (migration_31 + migration_45 marketplace_id) ────────────────────

CREATE TABLE IF NOT EXISTS pricing.ebay_scraped_sold (
    scrape_id         BIGSERIAL    PRIMARY KEY,
    item_id           TEXT         NOT NULL UNIQUE,
    title             TEXT         NOT NULL,
    source_product_id BIGINT       REFERENCES pricing.source_product(source_product_id),
    price_cents       INTEGER      NOT NULL CHECK (price_cents >= 0),
    currency          VARCHAR(3)   NOT NULL DEFAULT 'USD',
    condition_id      SMALLINT     REFERENCES pricing.card_condition(condition_id),
    finish_id         SMALLINT     NOT NULL DEFAULT pricing.default_finish_id(),
    language_id       SMALLINT     NOT NULL DEFAULT card_catalog.default_language_id(),
    sold_at           TIMESTAMPTZ  NOT NULL,
    scraped_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    promoted_to_obs   BOOLEAN      NOT NULL DEFAULT false,
    marketplace_id    VARCHAR(20)  NOT NULL DEFAULT 'EBAY-US'
);

CREATE INDEX IF NOT EXISTS idx_ebay_scraped_unpromoted
    ON pricing.ebay_scraped_sold (source_product_id)
    WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ebay_scraped_sold_at
    ON pricing.ebay_scraped_sold (sold_at DESC);

GRANT SELECT, INSERT, UPDATE ON pricing.ebay_scraped_sold
    TO app_backend, app_celery;

GRANT USAGE ON SEQUENCE pricing.ebay_scraped_sold_scrape_id_seq
    TO app_backend, app_celery;

-- ── FX Rates (migration_45) ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pricing.fx_rates (
    rate_date      DATE          NOT NULL,
    from_currency  VARCHAR(3)    NOT NULL,
    to_currency    VARCHAR(3)    NOT NULL DEFAULT 'USD',
    rate           NUMERIC(12,6) NOT NULL,
    fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, from_currency, to_currency)
);

GRANT SELECT, INSERT, UPDATE ON pricing.fx_rates
    TO app_backend, app_celery;

-- ── Shopify Staging Raw (transient buffer, TIMESTAMPTZ scraped_at per migration_58) ────

CREATE UNLOGGED TABLE IF NOT EXISTS pricing.shopify_staging_raw (
    product_id  BIGINT,
    date        DATE,
    variation   VARCHAR,
    price       NUMERIC,
    scraped_at  TIMESTAMPTZ,
    card_id     BIGINT,
    tcg_id      BIGINT,
    source_id   SMALLINT
);

COMMIT;
