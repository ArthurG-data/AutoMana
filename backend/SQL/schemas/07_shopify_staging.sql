-- Shopify Staging Tables and Procedures for Price Data ETL
-- All entities in pricing schema

-- Note: This table definition appears incomplete in the original
-- CREATE TABLE IF NOT EXISTS pricing.market_collection (
--     -- Add columns here
-- );

-- Staging table for raw Shopify price data
CREATE UNLOGGED TABLE IF NOT EXISTS pricing.shopify_staging_raw (
    product_id BIGINT,
    date DATE,
    variation VARCHAR,
    price NUMERIC,
    scraped_at TIMESTAMP,
    card_id BIGINT,
    tcg_id BIGINT
);

-- Note: This function definition appears incomplete in the original
-- CREATE OR REPLACE FUNCTION pricing.find_card_version(title TEXT)
-- RETURNS ... AS $$
-- BEGIN
--     -- Add function body here
-- END;
-- $$ LANGUAGE plpgsql;

-- Indexes for staging table
CREATE INDEX IF NOT EXISTS idx_shopify_staging_raw_product_id ON pricing.shopify_staging_raw(product_id);
CREATE INDEX IF NOT EXISTS idx_shopify_staging_raw_date ON pricing.shopify_staging_raw(date);     

-- Procedure: Load raw Shopify data into staging
CREATE OR REPLACE PROCEDURE pricing.raw_to_stage()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Create staging table if not exists
    CREATE UNLOGGED TABLE IF NOT EXISTS pricing.price_observation_stage (
        id SERIAL PRIMARY KEY,
        ts_date DATE NOT NULL,
        game_id INT NOT NULL REFERENCES pricing.card_game(game_id),
        print_id BIGINT NOT NULL,
        source_id INT NOT NULL REFERENCES pricing.price_source(source_id),
        metric_id INT NOT NULL REFERENCES pricing.price_metric(metric_id),
        value NUMERIC NOT NULL,
        scraped_at TIMESTAMP NOT NULL,
        condition_id INT REFERENCES pricing.card_condition(condition_id),
        finish_id INT REFERENCES pricing.card_finish(finish_id),
        UNIQUE(ts_date, game_id, print_id, source_id, metric_id, condition_id, finish_id)
    );

    -- Transform and load data
    WITH norm AS (
      SELECT
        ssr.date::date                  AS ts_date,
        cg.game_id                      AS game_id,
        ssr.product_id                  AS print_id,
        ps.source_id                    AS source_id,
        ssr.scraped_at                  AS scraped_at,
        ssr.price                       AS value,
        string_to_array(
          regexp_replace(trim(ssr.variation), '\s+', ' ', 'g'),
          ' '
        )                               AS parts
      FROM pricing.shopify_staging_raw ssr
      JOIN pricing.card_game     cg ON cg.code = 'mtg'
      JOIN pricing.price_source  ps ON ps.code = 'gg_brisbane'
    ),
    split AS (
      SELECT
        ts_date, game_id, print_id, source_id, value, scraped_at,
        /* condition = all words except the last only if last is "Foil" */
        CASE
          WHEN lower(parts[cardinality(parts)]) = 'foil'
            THEN array_to_string(parts[1:cardinality(parts)-1], ' ')
          ELSE array_to_string(parts, ' ')
        END                                          AS condition_name,
        /* finish = "Foil" or NULL (non-foil) */
        CASE
          WHEN lower(parts[cardinality(parts)]) = 'foil'
            THEN 'foil'
          ELSE 'nonfoil'
        END                                          AS finish_name,

        CASE
            WHEN lower(parts[cardinality(parts)]) = 'foil'
              THEN 2
            ELSE 3
          END AS metric_id
        FROM norm
    ),
    lookups AS (
      SELECT
        s.ts_date,
        s.game_id,
        s.print_id,
        s.source_id,
        s.metric_id,
        s.scraped_at,
        s.value,
        cc.condition_id                                       AS condition_id,
        cf.finish_id                                          AS finish_id
      FROM split s
      JOIN pricing.card_condition cc
        ON lower(cc.description) = lower(s.condition_name)
      /* finish_id only when Foil; otherwise NULL */
      LEFT JOIN pricing.card_finish cf
        ON s.finish_name IS NOT NULL AND lower(cf.code) = 'foil'
    )
    INSERT INTO pricing.price_observation_stage 
      (ts_date, game_id, print_id, source_id, metric_id, value, scraped_at, condition_id, finish_id)
    SELECT
      ts_date, game_id, print_id, source_id, metric_id, value, scraped_at, condition_id, finish_id
    FROM lookups;
END;
$$;

-- Procedure: Load from staging to final price observation table
CREATE OR REPLACE PROCEDURE pricing.stage_to_price_observation()
LANGUAGE plpgsql
AS $$
DECLARE
    v_count           bigint;
    v_not_found_count bigint;
    v_start_time      timestamp := clock_timestamp();
    v_step_time       timestamp;
BEGIN
    ------------------------------------------------------------------
    -- 1) Insert price observations
    ------------------------------------------------------------------
    v_step_time := clock_timestamp();

    INSERT INTO pricing.price_observation
        (ts_date, game_id, print_id, source_id, metric_id, value, scraped_at, condition_id, finish_id)
    SELECT
        ts_date, game_id, print_id, source_id, metric_id, value, scraped_at, condition_id, finish_id
    FROM pricing.price_observation_stage
    ON CONFLICT DO NOTHING;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE INFO 'Inserted % rows into price_observation in %',
               v_count, clock_timestamp() - v_step_time;

    ------------------------------------------------------------------
    -- 2) Insert external identifiers (gg_brisbane_id)
    ------------------------------------------------------------------
    v_step_time := clock_timestamp();

    INSERT INTO card_catalog.card_external_identifier
        (card_identifier_ref_id, card_version_id, value)
    SELECT
        cir2.card_identifier_ref_id,
        cce1.card_version_id,
        ssr.product_id::TEXT
    FROM pricing.shopify_staging_raw ssr
    JOIN card_catalog.card_identifier_ref cir1
         ON cir1.identifier_name = 'tcgplayer_id'
    JOIN card_catalog.card_external_identifier cce1
         ON cce1.card_identifier_ref_id = cir1.card_identifier_ref_id
        AND cce1.value::bigint = ssr.tcg_id
    JOIN card_catalog.card_identifier_ref cir2
         ON cir2.identifier_name = 'gg_brisbane_id'
    ON CONFLICT DO NOTHING;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE INFO 'Inserted % rows into card_external_identifier in %',
               v_count, clock_timestamp() - v_step_time;

    ------------------------------------------------------------------
    -- 3) Count tcg_ids with no mapping (not found)
    ------------------------------------------------------------------
    v_step_time := clock_timestamp();

    SELECT COUNT(*)
    INTO v_not_found_count
    FROM pricing.shopify_staging_raw ssr
    WHERE NOT EXISTS (
        SELECT 1
        FROM card_catalog.card_identifier_ref cir1
        JOIN card_catalog.card_external_identifier cce1
          ON cce1.card_identifier_ref_id = cir1.card_identifier_ref_id
         AND cce1.value::bigint = ssr.tcg_id
        WHERE cir1.identifier_name = 'tcgplayer_id'
    );

    RAISE INFO 'tcg_ids not found in card_external_identifier: % (checked in %)',
               v_not_found_count, clock_timestamp() - v_step_time;

    ------------------------------------------------------------------
    -- 4) Total time
    ------------------------------------------------------------------
    RAISE INFO 'Total procedure time: %', clock_timestamp() - v_start_time;
END;
$$;