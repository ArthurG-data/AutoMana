BEGIN;

CREATE TABLE IF NOT EXISTS pricing.mtgjson_staging (
  cardFinish TEXT,
  currency TEXT,
  date DATE,
  gameAvailability TEXT,
  price FLOAT,
  priceProvider TEXT,
  providerListing TEXT,
  uuid TEXT,
    -- Audit
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

-- NOTE: `pricing.mtgjson_payloads` and `pricing.process_mtgjson_payload`
-- were removed as part of the streaming-refactor. The raw .xz payload is
-- no longer archived as JSONB in the database — it's streamed directly
-- from disk into `pricing.mtgjson_card_prices_staging` via lzma + ijson +
-- asyncpg COPY (see staging.mtgjson.stream_to_staging in data_loader.py,
-- and docs/MTGJSON_PIPELINE.md for the design rationale). Do not re-add
-- either object without revisiting that decision first.

CREATE TABLE IF NOT EXISTS pricing.mtgjson_card_prices_staging (
    id SERIAL PRIMARY KEY,
    card_uuid TEXT NOT NULL,
    price_source TEXT NOT NULL,      -- provenance (tcgplayer, cardmarket, ...)
    price_type  TEXT,                -- buylist, retail
    finish_type TEXT NOT NULL,       -- foil, nonfoil, etched, showcase
    currency TEXT NOT NULL,
    price_value FLOAT NOT NULL,
    price_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Promote staged rows into pricing.price_observation.
-- No `p_payload_id` parameter — the streaming pipeline writes rows without
-- payload provenance (see stream_to_staging service), so there's no payload
-- to scope by. The proc processes the entire staging table in batch_days
-- windows and deletes rows it successfully resolves.
CREATE OR REPLACE PROCEDURE pricing.load_price_observation_from_mtgjson_staging_batched(
   batch_days int DEFAULT 30
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_data_provider_id bigint;

  v_min date;
  v_max date;
  v_start date;
  v_end date;

  v_upserted bigint := 0;
  v_deleted  bigint := 0;
  v_total_upserted bigint := 0;
  v_total_deleted  bigint := 0;
  v_is_ok boolean := false;
BEGIN
  IF batch_days IS NULL OR batch_days <= 0 THEN
    RAISE EXCEPTION 'batch_days must be > 0 (got %)', batch_days;
  END IF;

  -- normalize finish
  UPDATE pricing.mtgjson_card_prices_staging
  SET finish_type = 'NONFOIL'
  WHERE lower(finish_type) = 'normal';

  -- normalize tcgplayer
  UPDATE pricing.mtgjson_card_prices_staging
  SET price_source = 'tcg'
  WHERE lower(price_source) = 'tcgplayer';

  -- normalize sell and buy (transaction_type_code)
  UPDATE pricing.mtgjson_card_prices_staging
  SET price_type = CASE
    WHEN lower(price_type) IN ('retail', 'market') THEN 'sell'
    WHEN lower(price_type) IN ('buylist', 'directlow') THEN 'buy'
    ELSE lower(price_type)
  END;

  -- provider
  SELECT dp.data_provider_id
  INTO v_data_provider_id
  FROM pricing.data_provider dp
  WHERE dp.code = 'mtgjson'
  LIMIT 1;

  IF v_data_provider_id IS NULL THEN
    RAISE EXCEPTION 'Missing pricing.data_provider row with code=mtgjson';
  END IF;

  -- staging span
  SELECT min(price_date)::date, max(price_date)::date
  INTO v_min, v_max
  FROM pricing.mtgjson_card_prices_staging
  WHERE price_date IS NOT NULL;

  IF v_min IS NULL THEN
    RAISE NOTICE 'No rows in pricing.mtgjson_card_prices_staging to process.';
    RETURN;
  END IF;

  v_start := v_min;

  WHILE v_start <= v_max LOOP
    v_end := (v_start + (batch_days - 1));

    BEGIN
      v_is_ok := false;
      -- upsert price sources for this batch
      INSERT INTO pricing.price_source (code, name, currency_code)
      SELECT DISTINCT s.price_source, s.price_source, s.currency
      FROM pricing.mtgjson_card_prices_staging s
      WHERE s.price_date::date BETWEEN v_start AND v_end
        AND s.price_source IS NOT NULL
        AND s.currency IS NOT NULL
      ON CONFLICT (code) DO NOTHING;

      -- upsert finishes for this batch (IMPORTANT)
      INSERT INTO pricing.card_finished (code)
      SELECT DISTINCT UPPER(s.finish_type)
      FROM pricing.mtgjson_card_prices_staging s
      WHERE s.price_date::date BETWEEN v_start AND v_end
        AND s.finish_type IS NOT NULL
      ON CONFLICT (code) DO NOTHING;

      -- upsert observations
      with src AS (
        SELECT ps.source_id, ps.name, ps.currency_code
        FROM pricing.price_source ps
      ),
      fin AS (
        SELECT cf.finish_id, cf.code
        FROM pricing.card_finished cf
      ),
      cv AS (
        SELECT
          cei.value::uuid AS card_uuid,
          cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = 'mtgjson_id'
      ),
      prod AS (
        SELECT
          cv.card_version_id,
	 cv.card_uuid, 
          mcp.product_id
        FROM cv
        JOIN pricing.mtg_card_products mcp
          ON mcp.card_version_id = cv.card_version_id
      ),
  pairs AS (
    SELECT DISTINCT
      p.product_id,
      s.source_id
    FROM pricing.mtgjson_card_prices_staging st
    JOIN src s
      ON s.name = st.price_source
    AND s.currency_code = st.currency
    JOIN prod p
      ON p.card_uuid::uuid = st.card_uuid::uuid
  -- WHERE st.price_date::date BETWEEN v_start AND v_end
    where st.price_date IS NOT NULL
      AND st.card_uuid IS NOT NULL
      AND st.price_source IS NOT NULL
      AND st.currency IS NOT NULL
  ),
  insert_product_source AS (
    INSERT INTO pricing.source_product (product_id, source_id)
    SELECT product_id, source_id
    FROM pairs
    ON CONFLICT (product_id, source_id) DO NOTHING--option 3
  ),
        staged AS (
          SELECT
            s.id,
            s.price_date::date AS ts_date,
            s.price_source,
            tt.transaction_type_id AS price_type_id,
            s.currency,
            s.finish_type,
            s.card_uuid,
            round((s.price_value::numeric) * 100)::int AS price_cents
          FROM pricing.mtgjson_card_prices_staging s
          JOIN pricing.transaction_type tt
            ON tt.transaction_type_code = s.price_type
          --WHERE s.price_date::date BETWEEN v_start AND v_end
            AND s.price_date IS NOT NULL
            AND s.card_uuid  IS NOT NULL
            AND s.price_source IS NOT NULL
            AND s.currency   IS NOT NULL
            AND s.finish_type IS NOT NULL
            AND s.price_value IS NOT NULL
        ) ,resolved AS (
          SELECT
            st.id,
            st.ts_date,
            fin.finish_id,
            pricing.default_condition_id() AS condition_id,
            card_catalog.default_language_id() AS language_id,
            st.price_cents,
            st.price_type_id,
    sp.source_id, 
            sp.source_product_id
          FROM staged st
          JOIN src
            ON src.name = st.price_source
          AND src.currency_code = st.currency
          JOIN fin
            ON fin.code = st.finish_type
          JOIN prod
          ON prod.card_uuid::uuid = st.card_uuid::uuid
          JOIN pricing.source_product sp
            ON sp.product_id = prod.product_id 
        --  AND sp.source_id  = src.source_id
        ),
        upserted AS (
          INSERT INTO pricing.price_observation (
            ts_date,
            price_type_id,
            finish_id,
            condition_id,
            language_id,
            list_low_cents,
            list_avg_cents,
            sold_avg_cents,
            list_count,
            sold_count,
            source_product_id,
            data_provider_id,
            scraped_at,
            created_at,
            updated_at
          )
          SELECT
            r.ts_date,
            r.price_type_id,
            r.finish_id,
            r.condition_id,
            r.language_id,
            NULL::int,
            NULL::int,
            r.price_cents,     -- your choice: always sold_avg
            NULL::int,
            1,
            r.source_product_id,
            v_data_provider_id,
            now(), now(), now()
          FROM resolved r
          ON CONFLICT (ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)
          DO UPDATE SET
            sold_avg_cents = EXCLUDED.sold_avg_cents,
            sold_count     = EXCLUDED.sold_count,
            scraped_at     = EXCLUDED.scraped_at,
            updated_at     = now()
          RETURNING 1
        )
        SELECT count(*) INTO v_upserted FROM upserted;

      -- delete only rows that resolved (same resolution logic) -- the card from store has been insert
      WITH
      src AS (
        SELECT ps.source_id, ps.name, ps.currency_code
        FROM pricing.price_source ps
      ),
      fin AS (
        SELECT cf.finish_id, cf.code
        FROM pricing.card_finished cf
      ),
      cv AS (
        SELECT
          cei.value::uuid AS card_uuid,
          cei.card_version_id
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = 'mtgjson_id'
      ),
      prod AS (
        SELECT
          cv.card_version_id,
          cv.card_uuid,
          mcp.product_id
        FROM cv
        JOIN pricing.mtg_card_products mcp
          ON mcp.card_version_id = cv.card_version_id
      ),
      staged AS (
        SELECT
          s.id,
          s.price_source,
          s.currency,
          s.finish_type,
          s.card_uuid,
          s.price_type
        FROM pricing.mtgjson_card_prices_staging s
        WHERE s.price_date::date BETWEEN v_start AND v_end
          AND s.price_date IS NOT NULL
          AND s.card_uuid  IS NOT NULL
          AND s.price_source IS NOT NULL
          AND s.currency   IS NOT NULL
          AND s.finish_type IS NOT NULL
          AND s.price_value IS NOT NULL
      ),
      resolved_ids AS (
        SELECT st.id
        FROM staged st
        JOIN pricing.transaction_type tt
          ON tt.transaction_type_code = st.price_type
        JOIN src
          ON src.name = st.price_source AND src.currency_code = st.currency
        JOIN fin
          ON fin.code = st.finish_type
        JOIN prod
          ON prod.card_uuid::uuid = st.card_uuid::uuid --gere we want to find 
        JOIN pricing.source_product sp
          ON sp.product_id = prod.product_id
         AND sp.source_id  = src.source_id
      )
      DELETE FROM pricing.mtgjson_card_prices_staging s
      USING resolved_ids r
      WHERE s.id = r.id;

      GET DIAGNOSTICS v_deleted = ROW_COUNT;

      v_total_upserted := v_total_upserted + coalesce(v_upserted, 0);
      v_total_deleted  := v_total_deleted  + coalesce(v_deleted, 0);

      v_is_ok := true;
    EXCEPTION WHEN OTHERS THEN
      v_is_ok := false;
      RAISE;
    END;

    IF v_is_ok THEN
      RAISE NOTICE 'Batch % to %: upserted %, deleted %',
          v_start, v_end, v_upserted, v_deleted;
      COMMIT;
    ELSE
       RAISE NOTICE 'Batch % to % failed, rolling back. Upserted %, deleted %',
          v_start, v_end, v_upserted, v_deleted;
        ROLLBACK;
    END IF;
    v_start := v_end + 1;
  END LOOP;

  RAISE NOTICE 'Done. Total upserted %, total deleted %', v_total_upserted, v_total_deleted;
END;
$$;

COMMIT;
