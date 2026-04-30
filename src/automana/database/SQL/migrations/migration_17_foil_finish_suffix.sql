-- Migration 17: Foil-treatment finish suffix mapping
--
-- Adds pricing.mtgstock_name_finish_suffix, new finish codes (SURGE_FOIL,
-- RIPPLE_FOIL, RAINBOW_FOIL), and updates the three pricing procedures to:
--   1. Accept "Base Name (Foil Treatment)" names in the set+collector fallback
--      name check (resolves ~403 K foil-treatment reject rows).
--   2. Assign the granular finish_id from the suffix table instead of the
--      generic FOIL finish_id during promotion.
-- Safe to re-run: all INSERTs use ON CONFLICT DO NOTHING.
-- Applies to: load_staging_prices_batched, load_prices_from_staged_batched,
--             resolve_price_rejects.

BEGIN;

-- -----------------------------------------------------------------------
-- 1) New finish codes
-- -----------------------------------------------------------------------
INSERT INTO pricing.card_finished (code, description) VALUES
  ('SURGE_FOIL',   'Surge Foil'),
  ('RIPPLE_FOIL',  'Ripple Foil'),
  ('RAINBOW_FOIL', 'Rainbow Foil')
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------
-- 2) Suffix mapping table
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pricing.mtgstock_name_finish_suffix (
    suffix     TEXT PRIMARY KEY,
    finish_id  SMALLINT NOT NULL REFERENCES pricing.card_finished(finish_id)
);

INSERT INTO pricing.mtgstock_name_finish_suffix (suffix, finish_id) VALUES
  ('Surge Foil',    (SELECT finish_id FROM pricing.card_finished WHERE code = 'SURGE_FOIL')),
  ('Ripple Foil',   (SELECT finish_id FROM pricing.card_finished WHERE code = 'RIPPLE_FOIL')),
  ('Rainbow Foil',  (SELECT finish_id FROM pricing.card_finished WHERE code = 'RAINBOW_FOIL')),
  ('Foil Etched',   (SELECT finish_id FROM pricing.card_finished WHERE code = 'ETCHED')),
  ('Ripper Foil',   (SELECT finish_id FROM pricing.card_finished WHERE code = 'FOIL')),
  ('Textured Foil', (SELECT finish_id FROM pricing.card_finished WHERE code = 'FOIL'))
ON CONFLICT (suffix) DO NOTHING;

-- -----------------------------------------------------------------------
-- 3) load_staging_prices_batched — updated tmp_map_fallback name check
--    and _prom_batch finish_id derivation.
-- -----------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched(source_name VARCHAR(20), batch_days int DEFAULT 30, p_ingestion_run_id INT DEFAULT NULL)
LANGUAGE plpgsql
AS $$
DECLARE
  v_min date;
  v_max date;
  v_start date;
  v_end   date;
  v_source_id SMALLINT;
  v_ok boolean;
  v_mtg_game_id SMALLINT;
  v_data_provider_id SMALLINT;
  cur_rows bigint;
  total_inserted bigint := 0;
  v_batch_seq   INT := 0;
  v_batch_start TIMESTAMPTZ;
  v_total_days  INT;
  -- Promotion dimension IDs — resolved once before the loop
  v_price_type_id      int;
  v_finish_foil_id     smallint;
  v_finish_default_id  smallint;
  v_condition_id       smallint;
  v_language_id        smallint;
  -- Per-batch promotion counters
  v_prom_rows          bigint;
  v_prom_deleted       bigint;
  total_promoted       bigint := 0;
  total_staged_drained bigint := 0;

BEGIN
  -- determine overall date range from raw data
  SET LOCAL work_mem = '512MB';
  SET LOCAL maintenance_work_mem = '1GB';
  -- NOTE: temp_buffers cannot be changed after first temp-table access in a
  -- session, so it is NOT set here.  The target value (256 MB = 32768 pages)
  -- is pre-configured at pool-connection time via asyncpg server_settings in
  -- core/database.py, which makes this SET LOCAL a no-op on pool-recycled
  -- connections and avoids InvalidParameterValueError on second+ invocations.
  SET LOCAL synchronous_commit = off;
  SET LOCAL max_parallel_workers_per_gather = 4;

  SELECT min(ts_date), max(ts_date) INTO v_min, v_max FROM pricing.raw_mtg_stock_price;
  IF v_min IS NULL THEN
    RAISE NOTICE 'load_staging_prices_batched: no rows in raw_mtg_stock_price';
    RETURN;
  END IF;
  v_total_days := (v_max - v_min) + 1;

  SELECT ps.source_id INTO v_source_id
  FROM pricing.price_source ps
  WHERE ps.code = source_name;

  IF v_source_id IS NULL THEN
    RAISE EXCEPTION 'Missing source_code=% in pricing.price_source', source_name;
  END IF;

  SELECT dp.data_provider_id INTO v_data_provider_id
  FROM pricing.data_provider dp
  WHERE dp.code = 'mtgstocks';

  IF v_data_provider_id IS NULL THEN
    RAISE EXCEPTION 'Missing pricing.data_provider row with code=mtgstocks';
  END IF;

  SELECT cg.game_id INTO v_mtg_game_id
  FROM card_catalog.card_games_ref cg
  WHERE lower(cg.code) IN ('mtg', 'magic', 'magic_the_gathering')
  ORDER BY CASE lower(cg.code) WHEN 'mtg' THEN 1 ELSE 2 END
  LIMIT 1;

  v_start := v_min;

  -- Resolve promotion dimension IDs once — stable across all batches.
  v_finish_default_id := pricing.default_finish_id();
  SELECT cf.finish_id INTO v_finish_foil_id
  FROM pricing.card_finished cf
  WHERE lower(cf.code) IN ('foil', 'foiled', 'premium')
  ORDER BY cf.finish_id LIMIT 1;
  IF v_finish_foil_id IS NULL THEN
    v_finish_foil_id := v_finish_default_id;
  END IF;
  SELECT tt.transaction_type_id INTO v_price_type_id
  FROM pricing.transaction_type tt
  WHERE lower(tt.transaction_type_code) = 'sell'
  ORDER BY tt.transaction_type_id LIMIT 1;
  IF v_price_type_id IS NULL THEN
    RAISE EXCEPTION 'No ''sell'' row in pricing.transaction_type';
  END IF;
  v_condition_id := pricing.default_condition_id();
  v_language_id  := card_catalog.default_language_id();

  WHILE v_start <= v_max LOOP
    v_batch_seq   := v_batch_seq + 1;
    v_batch_start := clock_timestamp();
    v_end := LEAST(v_start + (batch_days - 1), v_max);
    v_ok :=false;
    BEGIN
      SET LOCAL work_mem                    = '512MB';
      SET LOCAL maintenance_work_mem        = '1GB';
      SET LOCAL synchronous_commit          = off;
      SET LOCAL max_parallel_workers_per_gather = 4;

      RAISE NOTICE 'Loading raw -> staging for % to %', v_start, v_end;

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
        s.cardtrader_id,
        v_data_provider_id AS data_provider_id
      FROM pricing.raw_mtg_stock_price s
      WHERE s.ts_date >= v_start
        AND s.ts_date <= v_end;

      DROP TABLE IF EXISTS tmp_batch_foil_split;
      CREATE TEMP TABLE tmp_batch_foil_split ON COMMIT DROP AS
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
        (v.list_low_cents * 100)::int AS list_low_cents,
        (v.list_avg_cents * 100)::int AS list_avg_cents,
        (v.sold_avg_cents * 100)::int AS sold_avg_cents,
        v.is_foil,
        v.value,
        r.data_provider_id
      FROM tmp_raw_batch r
      CROSS JOIN LATERAL (VALUES
        (r.price_low, r.price_avg, r.price_market, false,
         COALESCE(r.price_avg, r.price_market, r.price_low)),
        (NULL::numeric, r.price_foil, r.price_market_foil, true,
         COALESCE(r.price_foil, r.price_market_foil))
      ) AS v(list_low_cents, list_avg_cents, sold_avg_cents, is_foil, value)
      WHERE v.value IS NOT NULL;

      DROP TABLE IF EXISTS tmp_map_print;
      CREATE TEMP TABLE tmp_map_print ON COMMIT DROP AS
      SELECT DISTINCT
        u.print_id,
        cei.card_version_id
      FROM tmp_batch_foil_split u
      JOIN card_catalog.card_identifier_ref cir
        ON cir.identifier_name = 'mtgstock_id'
      JOIN card_catalog.card_external_identifier cei
        ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
       AND cei.value = u.print_id::text
      WHERE u.print_id IS NOT NULL;

      DROP TABLE IF EXISTS tmp_map_external;
      CREATE TEMP TABLE tmp_map_external ON COMMIT DROP AS
      WITH candidates AS (
        SELECT u.print_id
          , 'scryfall_id'::text   AS identifier_name
          , COALESCE(m.new_scryfall_id::text, u.scryfall_id) AS identifier_value, 1 AS prio
        FROM tmp_raw_batch u
        LEFT JOIN card_catalog.scryfall_migration m
          ON NULLIF(u.scryfall_id,'')::uuid = m.old_scryfall_id
         AND m.migration_strategy IN ('merge','move')
         AND m.new_scryfall_id IS NOT NULL
        WHERE u.scryfall_id IS NOT NULL AND u.scryfall_id <> ''

        UNION ALL
        SELECT u.print_id, 'tcgplayer_id'::text, u.tcg_id, 2
        FROM tmp_raw_batch u WHERE u.tcg_id IS NOT NULL

        UNION ALL
        SELECT u.print_id, 'cardtrader_id'::text, u.cardtrader_id, 3
        FROM tmp_raw_batch u WHERE u.cardtrader_id IS NOT NULL
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

      -- fallback by set + collector; relaxed name check allows "Name (Foil Suffix)"
      DROP TABLE IF EXISTS tmp_map_fallback;
      CREATE TEMP TABLE tmp_map_fallback ON COMMIT DROP AS
      SELECT DISTINCT
        u.set_abbr,
        u.collector_number,
        cv.card_version_id
      FROM tmp_raw_batch u
      JOIN card_catalog.sets sr
        ON LOWER(sr.set_code) = LOWER(u.set_abbr)
      JOIN card_catalog.card_version cv
        ON cv.set_id = sr.set_id
       AND cv.collector_number::text = u.collector_number
      LEFT JOIN card_catalog.unique_cards_ref uc
        ON uc.unique_card_id = cv.unique_card_id
      WHERE u.set_abbr IS NOT NULL
        AND u.collector_number IS NOT NULL
        AND (
            u.card_name IS NULL
            OR uc.card_name IS NULL
            OR lower(uc.card_name) = lower(u.card_name)
            OR lower(u.card_name) LIKE (lower(uc.card_name) || ' (%')
        );

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
      FROM tmp_batch_foil_split u
      LEFT JOIN tmp_map_print mp
        ON mp.print_id = u.print_id
      LEFT JOIN tmp_map_external me
        ON me.print_id = u.print_id
      LEFT JOIN tmp_map_fallback mf
        ON mf.set_abbr = u.set_abbr
       AND mf.collector_number = u.collector_number;

      WITH resolved_prints AS (
        SELECT DISTINCT r.print_id, r.card_version_id
        FROM tmp_resolved r
        WHERE r.print_id IS NOT NULL AND r.card_version_id IS NOT NULL
      ),
      unambiguous_print AS (
        SELECT rp.print_id, rp.card_version_id
        FROM resolved_prints rp
        JOIN (
          SELECT print_id
          FROM resolved_prints
          GROUP BY print_id
          HAVING count(DISTINCT card_version_id) = 1
        ) ok USING (print_id)
      ),
      pick_one_per_cv AS (
        SELECT DISTINCT ON (card_version_id)
          card_version_id,
          print_id::text AS print_value
        FROM unambiguous_print
        ORDER BY card_version_id, print_id
      ),
      mtgstock_ref AS (
        SELECT card_identifier_ref_id
        FROM card_catalog.card_identifier_ref
        WHERE identifier_name = 'mtgstock_id'
        LIMIT 1
      )
      INSERT INTO card_catalog.card_external_identifier (card_identifier_ref_id, card_version_id, value)
      SELECT r.card_identifier_ref_id, p.card_version_id, p.print_value
      FROM pick_one_per_cv p
      CROSS JOIN mtgstock_ref r
      LEFT JOIN card_catalog.card_external_identifier existing_pk
        ON existing_pk.card_version_id = p.card_version_id
       AND existing_pk.card_identifier_ref_id = r.card_identifier_ref_id
      WHERE existing_pk.card_version_id IS NULL
      ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING;

      INSERT INTO pricing.stg_price_observation_reject (
        ts_date, game_code, print_id, source_code, data_provider_id, scraped_at,
        list_low_cents, list_avg_cents, sold_avg_cents, is_foil, value,
        card_name, set_abbr, collector_number, scryfall_id, tcg_id, cardtrader_id,
        reject_reason
      )
      SELECT
        r.ts_date, r.game_code, r.print_id, r.source_code, r.data_provider_id, r.scraped_at,
        r.list_low_cents, r.list_avg_cents, r.sold_avg_cents, r.is_foil, r.value,
        r.card_name, r.set_abbr, r.collector_number, r.scryfall_id, r.tcg_id, r.cardtrader_id,
        'Could not resolve card_version_id via print_id/external_id/set+collector'
      FROM tmp_resolved r
      WHERE r.card_version_id IS NULL;

      WITH need AS (
        SELECT DISTINCT r.card_version_id
        FROM tmp_resolved r
        LEFT JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = r.card_version_id
        WHERE r.card_version_id IS NOT NULL AND mcp.product_id IS NULL
      ),
      gen AS (
        SELECT card_version_id, uuid_generate_v4() AS product_id FROM need
      ),
      ins_prod AS (
        INSERT INTO pricing.product_ref (product_id, game_id)
        SELECT product_id, v_mtg_game_id FROM gen
        ON CONFLICT (product_id) DO NOTHING
      )
      INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
      SELECT product_id, card_version_id FROM gen
      ON CONFLICT (card_version_id) DO NOTHING;

      DROP TABLE IF EXISTS tmp_product_lookup;
      CREATE TEMP TABLE tmp_product_lookup ON COMMIT DROP AS
      SELECT mcp.card_version_id, mcp.product_id
      FROM pricing.mtg_card_products mcp
      WHERE mcp.card_version_id IN (
        SELECT DISTINCT card_version_id FROM tmp_resolved WHERE card_version_id IS NOT NULL
      );

      INSERT INTO pricing.source_product (product_id, source_id)
      SELECT DISTINCT pl.product_id, v_source_id
      FROM tmp_product_lookup pl
      LEFT JOIN pricing.source_product sp
        ON sp.product_id = pl.product_id AND sp.source_id = v_source_id
      WHERE sp.source_product_id IS NULL
      ON CONFLICT (product_id, source_id) DO NOTHING;

      DROP TABLE IF EXISTS tmp_sp_lookup;
      CREATE TEMP TABLE tmp_sp_lookup ON COMMIT DROP AS
      SELECT pl.card_version_id, pl.product_id, sp.source_product_id
      FROM tmp_product_lookup pl
      JOIN pricing.source_product sp
        ON sp.product_id = pl.product_id AND sp.source_id = v_source_id;

      INSERT INTO pricing.stg_price_observation (
        ts_date, game_code, print_id, list_low_cents, list_avg_cents, sold_avg_cents,
        is_foil, source_code, data_provider_id, value,
        product_id, card_version_id, source_product_id,
        set_abbr, collector_number, card_name, scryfall_id, tcg_id, scraped_at
      )
      SELECT
        r.ts_date, r.game_code, r.print_id,
        r.list_low_cents, r.list_avg_cents, r.sold_avg_cents,
        r.is_foil, r.source_code, r.data_provider_id, r.value,
        l.product_id, r.card_version_id, l.source_product_id,
        r.set_abbr, r.collector_number, r.card_name, r.scryfall_id, r.tcg_id, r.scraped_at
      FROM tmp_resolved r
      JOIN tmp_sp_lookup l ON l.card_version_id = r.card_version_id
      WHERE r.card_version_id IS NOT NULL;

      GET DIAGNOSTICS cur_rows = ROW_COUNT;
      total_inserted := total_inserted + cur_rows;

      -- Inline promotion: drain staging rows for this date window immediately.
      -- finish_id uses suffix table for named foil treatments, falls back to
      -- the is_foil flag otherwise.
      DROP TABLE IF EXISTS _prom_batch;
      CREATE TEMP TABLE _prom_batch ON COMMIT DROP AS
      SELECT
        s.stg_id,
        s.ts_date,
        s.source_product_id,
        s.data_provider_id,
        v_price_type_id::int                              AS price_type_id,
        COALESCE(
            fsm.finish_id,
            CASE WHEN s.is_foil THEN v_finish_foil_id
                 ELSE v_finish_default_id END
        )                                                 AS finish_id,
        v_condition_id                                    AS condition_id,
        v_language_id                                     AS language_id,
        s.list_low_cents,
        s.list_avg_cents,
        s.sold_avg_cents,
        s.scraped_at
      FROM pricing.stg_price_observation s
      LEFT JOIN pricing.mtgstock_name_finish_suffix fsm
          ON s.card_name ~ '\([^)]+\)$'
         AND fsm.suffix = regexp_replace(s.card_name, '^.+\s+\(([^)]+)\)$', '\1')
      WHERE s.ts_date >= v_start
        AND s.ts_date <= v_end
        AND NOT (s.list_low_cents IS NULL
             AND s.list_avg_cents IS NULL
             AND s.sold_avg_cents IS NULL);

      DROP TABLE IF EXISTS _prom_dedup;
      CREATE TEMP TABLE _prom_dedup ON COMMIT DROP AS
      SELECT *
      FROM (
        SELECT b.*,
               row_number() OVER (
                 PARTITION BY
                   b.ts_date, b.source_product_id, b.price_type_id,
                   b.finish_id, b.condition_id, b.language_id, b.data_provider_id
                 ORDER BY b.scraped_at DESC, b.stg_id DESC
               ) AS rn
        FROM _prom_batch b
      ) x
      WHERE rn = 1;

      INSERT INTO pricing.price_observation (
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents, scraped_at
      )
      SELECT
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents, scraped_at
      FROM _prom_dedup
      ORDER BY ts_date
      ON CONFLICT (ts_date, source_product_id, price_type_id,
                   finish_id, condition_id, language_id, data_provider_id)
      DO UPDATE SET
        list_low_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_low_cents IS NOT NULL
            THEN EXCLUDED.list_low_cents
          ELSE pricing.price_observation.list_low_cents
        END,
        list_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_avg_cents IS NOT NULL
            THEN EXCLUDED.list_avg_cents
          ELSE pricing.price_observation.list_avg_cents
        END,
        sold_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.sold_avg_cents IS NOT NULL
            THEN EXCLUDED.sold_avg_cents
          ELSE pricing.price_observation.sold_avg_cents
        END,
        scraped_at = GREATEST(pricing.price_observation.scraped_at, EXCLUDED.scraped_at),
        updated_at = now();

      GET DIAGNOSTICS v_prom_rows = ROW_COUNT;
      total_promoted := total_promoted + v_prom_rows;

      DELETE FROM pricing.stg_price_observation s
      USING _prom_batch b
      WHERE s.stg_id = b.stg_id;

      GET DIAGNOSTICS v_prom_deleted = ROW_COUNT;
      total_staged_drained := total_staged_drained + v_prom_deleted;

      RAISE NOTICE 'Batch % to %: staged %, promoted %, drained %',
                   v_start, v_end, cur_rows, v_prom_rows, v_prom_deleted;
      v_ok := true;
    EXCEPTION WHEN OTHERS THEN
      RAISE WARNING 'Error processing batch % to %: %', v_start, v_end, SQLERRM;
      v_ok := false;
    END;

    if v_ok THEN
      COMMIT;
    ELSE
      ROLLBACK;
    END IF;
    IF p_ingestion_run_id IS NOT NULL THEN
      INSERT INTO ops.ingestion_step_batches (
        ingestion_run_step_id, batch_seq, range_start, range_end,
        status, items_ok, items_failed, duration_ms, error_details
      )
      SELECT
        st.id,
        v_batch_seq,
        EXTRACT(EPOCH FROM v_start)::bigint,
        EXTRACT(EPOCH FROM v_end)::bigint,
        CASE WHEN v_ok THEN 'success' ELSE 'failed' END,
        CASE WHEN v_ok THEN cur_rows ELSE 0 END,
        0,
        ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_batch_start)) * 1000)::int,
        jsonb_build_object('date_start', v_start::text, 'date_end', v_end::text,
                           'total_inserted', total_inserted,
                           'promoted', v_prom_rows)
      FROM ops.ingestion_run_steps st
      WHERE st.ingestion_run_id = p_ingestion_run_id
        AND st.step_name = 'raw_to_staging'
      LIMIT 1
      ON CONFLICT (ingestion_run_step_id, batch_seq) DO NOTHING;
      UPDATE ops.ingestion_run_steps
      SET progress = ROUND(100.0 * (v_end - v_min + 1) / NULLIF(v_total_days, 0), 2)
      WHERE ingestion_run_id = p_ingestion_run_id AND step_name = 'raw_to_staging';
      COMMIT;
    END IF;
    v_start := v_end + 1;
  END LOOP;
  RAISE NOTICE 'load_staging_prices_batched: total staged %, promoted %, drained %',
               total_inserted, total_promoted, total_staged_drained;
END;
$$;

-- -----------------------------------------------------------------------
-- 4) load_prices_from_staged_batched — updated _batch finish_id derivation.
--    Safety-net path for reject rows re-fed via resolve_price_rejects.
-- -----------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE pricing.load_prices_from_staged_batched(batch_days int DEFAULT 30)
LANGUAGE plpgsql
AS $$
DECLARE
  v_min date;
  v_max date;
  v_start date;
  v_end date;
  v_price_type_id      int;
  v_finish_foil_id     smallint;
  v_finish_default_id  smallint;
  v_condition_id       smallint;
  v_language_id        smallint;
  v_ok boolean;
  cur_rows      bigint;
  deleted_rows  bigint;
  inserted_rows bigint := 0;
  total_deleted bigint := 0;
BEGIN
  v_finish_default_id := pricing.default_finish_id();

  SELECT cf.finish_id
  INTO   v_finish_foil_id
  FROM   pricing.card_finished cf
  WHERE  lower(cf.code) IN ('foil', 'foiled', 'premium')
  ORDER  BY cf.finish_id
  LIMIT  1;

  IF v_finish_foil_id IS NULL THEN
    v_finish_foil_id := v_finish_default_id;
  END IF;

  SELECT tt.transaction_type_id
  INTO   v_price_type_id
  FROM   pricing.transaction_type tt
  WHERE  lower(tt.transaction_type_code) = 'sell'
  ORDER  BY tt.transaction_type_id
  LIMIT  1;

  IF v_price_type_id IS NULL THEN
    RAISE EXCEPTION 'No ''sell'' row in pricing.transaction_type; cannot load price_observation';
  END IF;

  v_condition_id := pricing.default_condition_id();
  v_language_id  := card_catalog.default_language_id();

  SELECT min(ts_date), max(ts_date)
  INTO   v_min, v_max
  FROM   pricing.stg_price_observation;

  IF v_min IS NULL THEN
    RAISE NOTICE 'load_prices_from_staged_batched: staging is empty, nothing to do';
    RETURN;
  END IF;

  RAISE NOTICE 'Loading price_observation from staging for % to %', v_min, v_max;

  v_start := v_min;
  WHILE v_start <= v_max LOOP
    v_end := LEAST(v_start + (batch_days - 1), v_max);
    v_ok  := false;

    BEGIN
      SET LOCAL work_mem          = '512MB';
      SET LOCAL maintenance_work_mem = '1GB';
      SET LOCAL synchronous_commit   = off;

      RAISE NOTICE 'Batch % to %', v_start, v_end;

      DROP TABLE IF EXISTS _batch;
      CREATE TEMP TABLE _batch ON COMMIT DROP AS
      SELECT
        s.stg_id,
        s.ts_date,
        s.source_product_id,
        s.data_provider_id,
        v_price_type_id::int                          AS price_type_id,
        COALESCE(
            fsm.finish_id,
            CASE WHEN s.is_foil THEN v_finish_foil_id
                 ELSE v_finish_default_id END
        )                                             AS finish_id,
        v_condition_id                                AS condition_id,
        v_language_id                                 AS language_id,
        s.list_low_cents,
        s.list_avg_cents,
        s.sold_avg_cents,
        s.scraped_at
      FROM pricing.stg_price_observation s
      LEFT JOIN pricing.mtgstock_name_finish_suffix fsm
          ON s.card_name ~ '\([^)]+\)$'
         AND fsm.suffix = regexp_replace(s.card_name, '^.+\s+\(([^)]+)\)$', '\1')
      WHERE s.ts_date >= v_start
        AND s.ts_date <= v_end
        AND NOT (s.list_low_cents IS NULL
             AND s.list_avg_cents IS NULL
             AND s.sold_avg_cents IS NULL);

      DROP TABLE IF EXISTS _dedup;
      CREATE TEMP TABLE _dedup ON COMMIT DROP AS
      SELECT *
      FROM (
        SELECT b.*,
               row_number() OVER (
                 PARTITION BY
                   b.ts_date, b.source_product_id, b.price_type_id,
                   b.finish_id, b.condition_id, b.language_id, b.data_provider_id
                 ORDER BY b.scraped_at DESC, b.stg_id DESC
               ) AS rn
        FROM _batch b
      ) x
      WHERE rn = 1;

      INSERT INTO pricing.price_observation (
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents, scraped_at
      )
      SELECT
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents, scraped_at
      FROM _dedup
      ORDER BY ts_date
      ON CONFLICT (ts_date, source_product_id, price_type_id,
                   finish_id, condition_id, language_id, data_provider_id)
      DO UPDATE SET
        list_low_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_low_cents IS NOT NULL
            THEN EXCLUDED.list_low_cents
          ELSE pricing.price_observation.list_low_cents
        END,
        list_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.list_avg_cents IS NOT NULL
            THEN EXCLUDED.list_avg_cents
          ELSE pricing.price_observation.list_avg_cents
        END,
        sold_avg_cents = CASE
          WHEN EXCLUDED.scraped_at >= pricing.price_observation.scraped_at
               AND EXCLUDED.sold_avg_cents IS NOT NULL
            THEN EXCLUDED.sold_avg_cents
          ELSE pricing.price_observation.sold_avg_cents
        END,
        scraped_at = GREATEST(pricing.price_observation.scraped_at, EXCLUDED.scraped_at),
        updated_at = now();

      GET DIAGNOSTICS cur_rows = ROW_COUNT;
      inserted_rows := inserted_rows + cur_rows;

      DELETE FROM pricing.stg_price_observation s
      USING _batch b
      WHERE s.stg_id = b.stg_id;

      GET DIAGNOSTICS deleted_rows = ROW_COUNT;
      total_deleted := total_deleted + deleted_rows;

      RAISE NOTICE 'Batch % to %: inserted/updated %, deleted % staging rows',
                   v_start, v_end, cur_rows, deleted_rows;

      v_ok := true;
    EXCEPTION WHEN OTHERS THEN
      RAISE WARNING 'Error processing batch % to %: % (SQLSTATE %)',
                    v_start, v_end, SQLERRM, SQLSTATE;
      v_ok := false;
    END;

    IF v_ok THEN
      COMMIT;
    ELSE
      ROLLBACK;
    END IF;
    v_start := v_end + 1;
  END LOOP;

  RAISE NOTICE 'load_prices_from_staged_batched: total inserted/updated %, total deleted from staging %',
               inserted_rows, total_deleted;
END;
$$;

-- -----------------------------------------------------------------------
-- 5) resolve_price_rejects — updated map_fb name check.
-- -----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION pricing.resolve_price_rejects(
    p_limit int DEFAULT 50000,
    p_only_unresolved boolean DEFAULT true
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
  v_source_id       smallint;
  v_mtg_game_id     smallint;
  v_inserted        bigint := 0;
  v_selected        bigint := 0;
  v_print_id        bigint := 0;
  v_external_id     bigint := 0;
  v_set_collector   bigint := 0;
  v_unresolved      bigint := 0;
  v_terminal_scry   bigint := 0;
BEGIN
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

  IF v_mtg_game_id IS NULL THEN
    RAISE EXCEPTION 'Could not resolve MTG game_id';
  END IF;

  DROP TABLE IF EXISTS tmp_rejects;
  CREATE TEMP TABLE tmp_rejects ON COMMIT DROP AS
  SELECT *
  FROM pricing.stg_price_observation_reject r
  WHERE (NOT p_only_unresolved) OR (r.resolved_at IS NULL AND is_terminal IS FALSE)
  ORDER BY r.resolution_attempted_at
  LIMIT p_limit;

  SELECT COUNT(*) INTO v_selected FROM tmp_rejects;
  RAISE NOTICE 'resolve_price_rejects: selected % candidates (only_unresolved=%)', v_selected, p_only_unresolved;

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
        AND m.migration_strategy IN ('merge', 'move')
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
      ON LOWER(s.set_code) = LOWER(r.set_abbr)
    JOIN card_catalog.card_version cv
      ON cv.set_id = s.set_id
     AND cv.collector_number::text = r.collector_number
    LEFT JOIN card_catalog.unique_cards_ref uc
      ON uc.unique_card_id = cv.unique_card_id
    WHERE r.set_abbr IS NOT NULL
      AND r.collector_number IS NOT NULL
      AND (
          r.card_name IS NULL
          OR uc.card_name IS NULL
          OR lower(uc.card_name) = lower(r.card_name)
          OR lower(r.card_name) LIKE (lower(uc.card_name) || ' (%')
      )
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

  SELECT
    COUNT(*) FILTER (WHERE resolution_method = 'PRINT_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'EXTERNAL_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'SET_COLLECTOR'),
    COUNT(*) FILTER (WHERE resolution_method = 'UNRESOLVED')
  INTO v_print_id, v_external_id, v_set_collector, v_unresolved
  FROM tmp_resolved;
  RAISE NOTICE 'resolve_price_rejects: PRINT_ID=% EXTERNAL_ID=% SET_COLLECTOR=% UNRESOLVED=%',
    v_print_id, v_external_id, v_set_collector, v_unresolved;

  WITH resolved_prints AS (
    SELECT DISTINCT r.print_id, r.card_version_id
    FROM tmp_resolved r
    WHERE r.card_version_id IS NOT NULL AND r.resolution_method <> 'PRINT_ID'
  ),
  unambiguous_print AS (
    SELECT rp.print_id, rp.card_version_id
    FROM resolved_prints rp
    JOIN (
      SELECT print_id FROM resolved_prints
      GROUP BY print_id HAVING count(DISTINCT card_version_id) = 1
    ) ok USING (print_id)
  ),
  pick_one_per_cv AS (
    SELECT DISTINCT ON (card_version_id)
      card_version_id,
      print_id::text AS print_value
    FROM unambiguous_print
    ORDER BY card_version_id, print_id
  ),
  mtgstock_ref AS (
    SELECT card_identifier_ref_id
    FROM card_catalog.card_identifier_ref
    WHERE identifier_name = 'mtgstock_id'
    LIMIT 1
  )
  INSERT INTO card_catalog.card_external_identifier (card_identifier_ref_id, card_version_id, value)
  SELECT r.card_identifier_ref_id, p.card_version_id, p.print_value
  FROM pick_one_per_cv p
  CROSS JOIN mtgstock_ref r
  LEFT JOIN card_catalog.card_external_identifier existing_pk
    ON existing_pk.card_version_id = p.card_version_id
   AND existing_pk.card_identifier_ref_id = r.card_identifier_ref_id
  WHERE existing_pk.card_version_id IS NULL
  ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING;

  WITH need AS (
    SELECT DISTINCT card_version_id FROM tmp_resolved
    WHERE card_version_id IS NOT NULL
    EXCEPT SELECT card_version_id FROM pricing.mtg_card_products
  ),
  gen AS (
    SELECT card_version_id, uuid_generate_v4() AS product_id FROM need
  ),
  ins_prod AS (
    INSERT INTO pricing.product_ref (product_id, game_id)
    SELECT product_id, v_mtg_game_id FROM gen
    ON CONFLICT (product_id) DO NOTHING
  )
  INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
  SELECT product_id, card_version_id FROM gen
  ON CONFLICT (card_version_id) DO NOTHING;

  INSERT INTO pricing.source_product (product_id, source_id)
  SELECT DISTINCT mcp.product_id, v_source_id
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = r.card_version_id
  LEFT JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id AND sp.source_id = v_source_id
  WHERE r.card_version_id IS NOT NULL AND sp.source_product_id IS NULL
  ON CONFLICT (product_id, source_id) DO NOTHING;

  INSERT INTO pricing.stg_price_observation (
    ts_date, game_code, print_id,
    list_low_cents, list_avg_cents, sold_avg_cents,
    is_foil, source_code, data_provider_id, value,
    product_id, card_version_id, source_product_id,
    set_abbr, collector_number, card_name, scryfall_id, tcg_id,
    scraped_at
  )
  SELECT
    r.ts_date, r.game_code, r.print_id,
    r.list_low_cents, r.list_avg_cents, r.sold_avg_cents,
    r.is_foil, r.source_code, r.data_provider_id, r.value,
    mcp.product_id, r.card_version_id, sp.source_product_id,
    r.set_abbr, r.collector_number, r.card_name, r.scryfall_id, r.tcg_id,
    r.scraped_at
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id AND sp.source_id = v_source_id
  WHERE r.card_version_id IS NOT NULL
    AND NOT (r.list_low_cents IS NULL
         AND r.list_avg_cents IS NULL
         AND r.sold_avg_cents IS NULL);

  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  RAISE NOTICE 'resolve_price_rejects: re-fed % rows into stg_price_observation', v_inserted;

  UPDATE pricing.stg_price_observation_reject rej
  SET
    resolved_at                = now(),
    resolved_card_version_id   = r.card_version_id,
    resolved_method            = r.resolution_method,
    resolved_product_id        = mcp.product_id,
    resolved_source_product_id = sp.source_product_id,
    is_terminal                = TRUE,
    terminal_reason            = 'Resolved via ' || r.resolution_method || ' mapping'
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id AND sp.source_id = v_source_id
  WHERE rej.ts_date          = r.ts_date
    AND rej.print_id         = r.print_id
    AND rej.is_foil          = r.is_foil
    AND rej.source_code      = r.source_code
    AND rej.data_provider_id = r.data_provider_id
    AND rej.scraped_at       = r.scraped_at
    AND r.card_version_id IS NOT NULL;

  UPDATE pricing.stg_price_observation_reject r
  SET
    resolved_at = now(),
    is_terminal = TRUE,
    terminal_reason = 'Scryfall migration delete and no alternative identifiers'
  FROM card_catalog.scryfall_migration m
  WHERE m.migration_strategy = 'delete'
    AND m.old_scryfall_id::text = r.scryfall_id;

  GET DIAGNOSTICS v_terminal_scry = ROW_COUNT;
  RAISE NOTICE 'resolve_price_rejects: marked % rows terminal (scryfall delete)', v_terminal_scry;

  RETURN v_inserted;
END;
$$;

-- Grant SELECT on new table to read roles
GRANT SELECT ON pricing.mtgstock_name_finish_suffix TO app_readonly;
GRANT SELECT, INSERT, UPDATE ON pricing.mtgstock_name_finish_suffix TO app_celery;
-- app_rw covers app_backend and other standard read/write roles
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.mtgstock_name_finish_suffix TO app_rw, app_admin;

COMMIT;
