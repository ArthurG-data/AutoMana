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

-- create hypertable
SELECT create_hypertable('pricing.price_observation',
                         by_range('ts_date'),
                         if_not_exists => TRUE);

-- Add a space (hash) dimension on print_id for parallelism & chunk fan-out:
SELECT add_dimension('pricing.price_observation', 'print_id', number_partitions => 8);

--set chunk time
SELECT set_chunk_time_interval('pricing.price_observation', INTERVAL '90 days');

CREATE INDEX IF NOT EXISTS idx_price_date ON pricing.price_observation(ts_date DESC);


ALTER TABLE pricing.price_observation
  SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'print_id',
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
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TABLE IF EXISTS pricing.stg_price_observation;
CREATE TABLE pricing.stg_price_observation (--make it a product already by linking to the card_version and product_ref, and translating the source and metric code to id in the same table to simplify the load in the dimension and fact table
ts_date       DATE        NOT NULL,
game_code     TEXT       NOT NULL,
print_id      BIGINT      NOT NULL,
metric_code     TEXT    NOT NULL,
source_code     TEXT    NOT NULL,
value         NUMERIC(12,4) NOT NULL,
scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now().
);

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
DROP TABLE IF EXISTS pricing.price_observation;


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
       timescaledb.compress_segmentby = 'print_id',
       timescaledb.compress_orderby   = 'ts_date DESC');

--translate code to id
CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched(batch_days int DEFAULT 30)
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
  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM pricing.raw_mtg_stock_price;
  IF v_min IS NULL THEN
    RAISE NOTICE 'load_staging_prices_batched: no rows in raw_mtg_stock_price';
    RETURN;
  END IF;

  v_start := v_min;
  WHILE v_start <= v_max LOOP
    v_end := LEAST(v_start + (batch_days - 1), v_max);

    RAISE NOTICE 'Loading raw -> staging for % to %', v_start, v_end;

    INSERT INTO pricing.stg_price_observation (
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
    FROM pricing.raw_mtg_stock_price s
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
DROP INDEX IF EXISTS dim_price_obs_ts_idx;
CREATE OR REPLACE PROCEDURE pricing.load_dim_from_staging( --to test
    p_ingestion_run_id INT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_source_id           pricing.price_source.source_id%TYPE;
    v_card_game_id        card_catalog.card_games_ref.game_id%TYPE;
    v_game_id             card_catalog.games_ref.game_id%TYPE;
    v_rows_inserted       BIGINT := 0;
    v_rows_missing_ids    BIGINT := 0;
    v_rows_missing_products BIGINT := 0;
BEGIN
    RAISE NOTICE 'Starting load_dim_from_staging with ingestion_run_id=%', p_ingestion_run_id;

    -- Create temp table to track unresolved IDs
    CREATE TEMP TABLE temp_missing_ids (
        print_id BIGINT,
        scryfall_id UUID,
        multiverse_id BIGINT,
        tcg_id BIGINT,
        error_reason TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    ) ON COMMIT PRESERVE ROWS;

    -- Fetch source_id once (MTGStocks)
    SELECT ps.source_id INTO v_source_id
    FROM pricing.price_source ps
    WHERE ps.code = 'mtgstocks';

    IF v_source_id IS NULL THEN
        RAISE EXCEPTION 'price_source with code=mtgstocks not found';
    END IF;

    -- Fetch game IDs
    SELECT game_id INTO v_card_game_id
    FROM card_catalog.card_games_ref
    WHERE code = 'mtg';

    SELECT game_id INTO v_game_id
    FROM card_catalog.games_ref
    WHERE game_description = 'paper';

    IF v_card_game_id IS NULL OR v_game_id IS NULL THEN
        RAISE EXCEPTION 'Could not resolve MTG game IDs';
    END IF;

    -- Insert into dim_price_observation with product creation workflow
    INSERT INTO pricing.dim_price_observation (
        ts_date, game_id, print_id, source_id, metric_id,
        product_source_id, value, scraped_at
    )
    WITH id_resolved AS (
        -- Link staging prices with external identifiers from ingestion mapping
        SELECT
            s.ts_date,
            v_card_game_id as game_id,
            s.print_id,
            ps.source_id,
            pm.metric_id,
            s.value,
            s.scraped_at,
            iim.scryfall_id,
            iim.multiverse_id,
            iim.tcg_id
        FROM pricing.stg_price_observation s
        JOIN card_catalog.card_games_ref cg ON cg.code = s.game_code
        JOIN pricing.price_source ps ON ps.code = s.source_code
        JOIN pricing.price_metric pm ON pm.code = s.metric_code
        LEFT JOIN ops.ingestion_ids_mapping iim 
            ON iim.mtgstock_id = s.print_id
            AND (p_ingestion_run_id IS NULL OR iim.ingestion_run_id = p_ingestion_run_id)
        WHERE s.value IS NOT NULL
    ),
    card_versions AS (
        -- Resolve card_version_id using external identifiers (priority: scryfall > tcg > multiverse)
        SELECT
            ir.ts_date, ir.game_id, ir.print_id, ir.source_id, ir.metric_id,
            ir.value, ir.scraped_at,
            COALESCE(
                -- Try scryfall_id
                (SELECT cei.card_version_id 
                 FROM card_catalog.card_external_identifier cei
                 JOIN card_catalog.card_identifier_ref cir
                   ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                 WHERE cir.identifier_name = 'scryfall_id'
                   AND ir.scryfall_id IS NOT NULL
                   AND cei.value = ir.scryfall_id::text
                 LIMIT 1),
                -- Try tcg_id
                (SELECT cei.card_version_id 
                 FROM card_catalog.card_external_identifier cei
                 JOIN card_catalog.card_identifier_ref cir
                   ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                 WHERE cir.identifier_name = 'tcgplayer_id'
                   AND ir.tcg_id IS NOT NULL
                   AND cei.value = ir.tcg_id::text
                 LIMIT 1),
                -- Try multiverse_id
                (SELECT cei.card_version_id 
                 FROM card_catalog.card_external_identifier cei
                 JOIN card_catalog.card_identifier_ref cir
                   ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                 WHERE cir.identifier_name = 'multiverse_id'
                   AND ir.multiverse_id IS NOT NULL
                   AND cei.value = ir.multiverse_id::text
                 LIMIT 1)
            ) AS card_version_id
        FROM id_resolved ir
    ),
    products_created AS (
        -- Get or create product_id and source_product_id
        SELECT
            cv.ts_date, cv.game_id, cv.print_id, cv.source_id, cv.metric_id,
            cv.value, cv.scraped_at,
            COALESCE(
                -- Try to get existing product_id
                (SELECT mcp.product_id
                 FROM pricing.mtg_card_products mcp
                 WHERE mcp.card_version_id = cv.card_version_id
                 LIMIT 1),
                -- Or create new product_id
                (SELECT uuid_generate_v4())
            ) AS product_id,
            cv.card_version_id
        FROM card_versions cv
        WHERE cv.card_version_id IS NOT NULL
    ),
    insert_products AS (
        -- Insert missing product_ref and mtg_card_products entries
        INSERT INTO pricing.product_ref (game_id)
        SELECT DISTINCT v_card_game_id
        FROM products_created pc
        WHERE NOT EXISTS (
            SELECT 1 FROM pricing.mtg_card_products mcp
            WHERE mcp.product_id = pc.product_id
        )
        GROUP BY game_id
        ON CONFLICT DO NOTHING
        RETURNING product_id
    ),
    insert_mtg_products AS (
        -- Link card_version to product
        INSERT INTO pricing.mtg_card_products (product_id, game_version_id, card_version_id)
        SELECT DISTINCT pc.product_id, v_game_id, pc.card_version_id
        FROM products_created pc
        WHERE NOT EXISTS (
            SELECT 1 FROM pricing.mtg_card_products mcp
            WHERE mcp.card_version_id = pc.card_version_id
        )
        ON CONFLICT (card_version_id) DO NOTHING
        RETURNING product_id
    ),
    source_products AS (
        -- Get or create source_product_id
        SELECT
            pc.ts_date, pc.game_id, pc.print_id, pc.source_id, pc.metric_id,
            pc.value, pc.scraped_at,
            COALESCE(
                (SELECT sp.source_product_id
                 FROM pricing.source_product sp
                 WHERE sp.product_id = pc.product_id AND sp.source_id = pc.source_id
                 LIMIT 1),
                (SELECT sp.source_product_id
                 FROM pricing.source_product sp
                 WHERE sp.product_id = pc.product_id AND sp.source_id = pc.source_id
                 LIMIT 1)
            ) AS source_product_id
        FROM products_created pc
    )
    SELECT
        sp.ts_date,
        sp.game_id,
        sp.print_id,
        sp.source_id,
        sp.metric_id,
        COALESCE(sp.source_product_id,
            (INSERT INTO pricing.source_product (product_id, source_id)
             VALUES (
                (SELECT product_id FROM products_created WHERE print_id = sp.print_id LIMIT 1),
                sp.source_id
             )
             ON CONFLICT (product_id, source_id) DO NOTHING
             RETURNING source_product_id)
        ) AS source_product_id,
        sp.value,
        sp.scraped_at
    FROM source_products sp
    ON CONFLICT DO NOTHING;

    GET DIAGNOSTICS v_rows_inserted = ROW_COUNT;

    -- Check for missing IDs
    SELECT COUNT(*) INTO v_rows_missing_ids
    FROM pricing.stg_price_observation s
    WHERE NOT EXISTS (
        SELECT 1 FROM ops.ingestion_ids_mapping iim
        WHERE iim.mtgstock_id = s.print_id
        AND (p_ingestion_run_id IS NULL OR iim.ingestion_run_id = p_ingestion_run_id)
    );

    RAISE NOTICE 'load_dim_from_staging complete: Inserted=%, MissingIDs=%',
        v_rows_inserted, v_rows_missing_ids;

END;
$$;

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