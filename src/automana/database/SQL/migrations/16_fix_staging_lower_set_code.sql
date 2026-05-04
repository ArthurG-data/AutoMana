-- Migration 16: Fix case-sensitive set_code comparison in staging procedures
--
-- Both pricing.load_staging_prices_batched and pricing.resolve_price_rejects
-- contained:
--     JOIN card_catalog.sets sr ON sr.set_code = u.set_abbr
-- PostgreSQL text equality is case-sensitive.  The catalog stores set codes
-- in lowercase ('evg'); raw_mtg_stock_price stores them in uppercase ('EVG').
-- The mismatch silently broke step-3 (SET_COLLECTOR) resolution for all
-- 56,817 print_ids, collapsing the link rate to ~24% (step 1 only).
--
-- Fix: LOWER(set_abbr) in both procedures (or LOWER both sides for robustness).
-- Idempotent: CREATE OR REPLACE is safe to re-run.

-- ─────────────────────────────────────────────────────────────────────────────
-- Re-create load_staging_prices_batched with the LOWER() fix.
-- Full body copied from src/automana/database/SQL/schemas/06_prices.sql.
-- ─────────────────────────────────────────────────────────────────────────────

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

  --will need to add the foil code translation in the same way as the metric code and source code translation
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
-----------------------------------------------
  SELECT cg.game_id INTO v_mtg_game_id
  FROM card_catalog.card_games_ref cg
  WHERE lower(cg.code) IN ('mtg', 'magic', 'magic_the_gathering')
  ORDER BY CASE lower(cg.code) WHEN 'mtg' THEN 1 ELSE 2 END
  LIMIT 1;

  -- stg_price_observation_reject is pre-created by 06_prices.sql schema section;
  -- app_celery only has USAGE on the pricing schema (not CREATE), so the
  -- CREATE TABLE IF NOT EXISTS that used to live here was removed.

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
      -- Session locals are cleared by the previous COMMIT, so re-apply.
      SET LOCAL work_mem                    = '512MB';
      SET LOCAL maintenance_work_mem        = '1GB';
      SET LOCAL synchronous_commit          = off;
      SET LOCAL max_parallel_workers_per_gather = 4;

      RAISE NOTICE 'Loading raw -> staging for % to %', v_start, v_end;
      
      -- -------------------------------------------------------------------------
      -- 1) Temp raw slice for this batch
      -- -------------------------------------------------------------------------
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
        -- Non-foil row: all three non-foil price fields; filter on any non-null price.
        (r.price_low, r.price_avg, r.price_market, false,
         COALESCE(r.price_avg, r.price_market, r.price_low)),
        -- Foil row: foil-specific prices only; filter on any non-null foil price.
        (NULL::numeric, r.price_foil, r.price_market_foil, true,
         COALESCE(r.price_foil, r.price_market_foil))
      ) AS v(list_low_cents, list_avg_cents, sold_avg_cents, is_foil, value)
      WHERE v.value IS NOT NULL;

      -- -------------------------------------------------------------------------
      -- 3) Resolve card_version_id with priority:
      --    (1) print map -> (2) external ids -> (3) set+collector (+name)
      -- -------------------------------------------------------------------------
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

  -- (2) external ids mapping (prefer scryfall > tcgplayer > cardtrader), keyed by print_id
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
    SELECT u.print_id, 'tcgplayer_id'::text  AS identifier_name, u.tcg_id        AS identifier_value, 2 AS prio
    FROM tmp_raw_batch u WHERE u.tcg_id IS NOT NULL

    UNION ALL
    SELECT u.print_id, 'cardtrader_id'::text AS identifier_name, u.cardtrader_id AS identifier_value, 3 AS prio
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

  -- (3) fallback by set + collector (+ optional name match)
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

  -- 3d) Final resolved rows — built from tmp_batch_foil_split so that each row
  --     already carries the foil-split price columns (list_low_cents, list_avg_cents,
  --     sold_avg_cents, is_foil, value) needed by the reject insert and the staging
  --     insert downstream. tmp_map_print / tmp_map_external / tmp_map_fallback are
  --     keyed by print_id / set_abbr+collector_number, which are present on both
  --     the raw and foil-split tables.
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

  -- -------------------------------------------------------------------------
  -- 3e) Backfill mtgstock_id mapping into identifier tables (if missing)
  --     Only when we have a resolved card_version_id and a print_id.
  --     Also avoids ambiguous print_id -> multiple card_version_id in this batch.
  -- -------------------------------------------------------------------------
  WITH resolved_prints AS (
    SELECT DISTINCT
      r.print_id,
      r.card_version_id
    FROM tmp_resolved r
    WHERE r.print_id IS NOT NULL
      AND r.card_version_id IS NOT NULL
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
  -- choose at most one print_id per card_version_id to avoid PK conflicts
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
  -- Explicit PK conflict target — a concurrent re-run that inserted the same
  -- (card_version_id, ref_id) between the LEFT JOIN check and the INSERT
  -- gets absorbed silently. The (ref_id, value) UNIQUE constraint no longer
  -- exists (per 02_card_schema.sql comments), so this clause covers only
  -- the PK case — which is exactly what we want here.
  INSERT INTO card_catalog.card_external_identifier (card_identifier_ref_id, card_version_id, value)
  SELECT
    r.card_identifier_ref_id,
    p.card_version_id,
    p.print_value
  FROM pick_one_per_cv p
  CROSS JOIN mtgstock_ref r
  LEFT JOIN card_catalog.card_external_identifier existing_pk
    ON existing_pk.card_version_id = p.card_version_id
  AND existing_pk.card_identifier_ref_id = r.card_identifier_ref_id
  WHERE existing_pk.card_version_id IS NULL
  ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING;

      -- -------------------------------------------------------------------------
      -- 4) Send unresolved rows to reject table (so you can inspect/repair mappings)
      -- -------------------------------------------------------------------------
      INSERT INTO pricing.stg_price_observation_reject (
        ts_date, game_code, print_id, source_code, data_provider_id,scraped_at,
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

      -- -------------------------------------------------------------------------
      -- 5) Ensure mtg_products exist for resolved card_version_id
      -- -------------------------------------------------------------------------
      WITH need AS (
    SELECT DISTINCT r.card_version_id
    FROM tmp_resolved r
    LEFT JOIN pricing.mtg_card_products mcp
      ON mcp.card_version_id = r.card_version_id
    WHERE r.card_version_id IS NOT NULL
      AND mcp.product_id IS NULL
  ),
  gen AS (
    SELECT card_version_id, uuid_generate_v4() AS product_id
    FROM need
  ),
  ins_prod AS (
    INSERT INTO pricing.product_ref (product_id, game_id)
    SELECT product_id, v_mtg_game_id
    FROM gen
    ON CONFLICT (product_id) DO NOTHING
  )
    INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
    SELECT product_id, card_version_id
    FROM gen
    ON CONFLICT (card_version_id) DO NOTHING;
      -- -------------------------------------------------------------------------
      -- 7) Build lookup: card_version_id -> product_id -> source_product_id
      -- -------------------------------------------------------------------------
      DROP TABLE IF EXISTS tmp_product_lookup;
      CREATE TEMP TABLE tmp_product_lookup ON COMMIT DROP AS
      SELECT mcp.card_version_id, mcp.product_id
      FROM pricing.mtg_card_products mcp
      WHERE mcp.card_version_id IN (SELECT DISTINCT card_version_id FROM tmp_resolved WHERE card_version_id IS NOT NULL);

      INSERT INTO pricing.source_product (product_id, source_id)
      SELECT DISTINCT pl.product_id, v_source_id
      FROM tmp_product_lookup pl
      LEFT JOIN pricing.source_product sp
        ON sp.product_id = pl.product_id
      AND sp.source_id = v_source_id
      WHERE sp.source_product_id IS NULL
      ON CONFLICT (product_id, source_id) DO NOTHING;

      DROP TABLE IF EXISTS tmp_sp_lookup;
      CREATE TEMP TABLE tmp_sp_lookup ON COMMIT DROP AS
      SELECT
        pl.card_version_id,
        pl.product_id,
        sp.source_product_id
      FROM tmp_product_lookup pl
      JOIN pricing.source_product sp
        ON sp.product_id = pl.product_id
      AND sp.source_id = v_source_id;
      -- -------------------------------------------------------------------------
      -- 8) Insert resolved rows into staging
      -- -------------------------------------------------------------------------
      INSERT INTO pricing.stg_price_observation ( --addinf ts date
        ts_date, game_code, print_id, list_low_cents, list_avg_cents, sold_avg_cents, is_foil, source_code, data_provider_id,  value,
        product_id, card_version_id, source_product_id,
        set_abbr, collector_number, card_name, scryfall_id, tcg_id,
        scraped_at
      )
      SELECT
        r.ts_date,
          r.game_code,
          r.print_id,
          r.list_low_cents,
          r.list_avg_cents,
          r.sold_avg_cents,
          r.is_foil,
          r.source_code,
          r.data_provider_id,
          r.value,
          l.product_id,
          r.card_version_id,
          l.source_product_id,
          r.set_abbr,
          r.collector_number,
          r.card_name,
          r.scryfall_id,
          r.tcg_id,
          r.scraped_at
      FROM tmp_resolved r
      JOIN tmp_sp_lookup l
        ON l.card_version_id = r.card_version_id
      WHERE r.card_version_id IS NOT NULL;

      GET DIAGNOSTICS cur_rows = ROW_COUNT;
      total_inserted := total_inserted + cur_rows;

      -- -----------------------------------------------------------------------
      -- Inline promotion: drain staging rows for this date window immediately.
      -- Keeps stg_price_observation from accumulating across the full run.
      -- Uses distinct temp-table names (_prom_batch/_prom_dedup) to avoid
      -- colliding with the _batch/_dedup names in load_prices_from_staged_batched.
      -- -----------------------------------------------------------------------
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
                   b.ts_date,
                   b.source_product_id,
                   b.price_type_id,
                   b.finish_id,
                   b.condition_id,
                   b.language_id,
                   b.data_provider_id
                 ORDER BY b.scraped_at DESC, b.stg_id DESC
               ) AS rn
        FROM _prom_batch b
      ) x
      WHERE rn = 1;

      INSERT INTO pricing.price_observation (
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents,
        scraped_at
      )
      SELECT
        ts_date, source_product_id, price_type_id,
        finish_id, condition_id, language_id, data_provider_id,
        list_low_cents, list_avg_cents, sold_avg_cents,
        scraped_at
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
    -- advance to next batch
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
  -- stg_price_obs_date_spid_foil_idx is pre-created by 06_prices.sql schema section;
  -- CREATE INDEX IF NOT EXISTS removed — same reason as CREATE TABLE above.
  RAISE NOTICE 'load_staging_prices_batched: total staged %, promoted %, drained %',
               total_inserted, total_promoted, total_staged_drained;
END;
$$;

------------------------------------------------------------------
--Step 2: Move from staging to dimensional model (price_observation), with any necessary transformations
------------------------------------------------------------------


ANALYZE pricing.stg_price_observation;

-- ─────────────────────────────────────────────────────────────────────────────
-- Re-create resolve_price_rejects with the LOWER() fix.
-- ─────────────────────────────────────────────────────────────────────────────

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
  -- mtgstock source
  SELECT ps.source_id INTO v_source_id
  FROM pricing.price_source ps
  WHERE ps.code = 'mtgstocks';

  IF v_source_id IS NULL THEN
    RAISE EXCEPTION 'Missing source_code=mtgstocks in pricing.price_source';
  END IF;

  -- MTG game id
  SELECT cg.game_id INTO v_mtg_game_id
  FROM card_catalog.card_games_ref cg
  WHERE lower(cg.code) IN ('mtg', 'magic', 'magic_the_gathering')
  ORDER BY CASE lower(cg.code) WHEN 'mtg' THEN 1 ELSE 2 END
  LIMIT 1;

  IF v_mtg_game_id IS NULL THEN
    RAISE EXCEPTION 'Could not resolve MTG game_id';
  END IF;

  -- pick a working set
  DROP TABLE IF EXISTS tmp_rejects;
  CREATE TEMP TABLE tmp_rejects ON COMMIT DROP AS
  SELECT *
  FROM pricing.stg_price_observation_reject r
  WHERE (NOT p_only_unresolved) OR (r.resolved_at IS NULL AND is_terminal IS FALSE)
  ORDER BY r.resolution_attempted_at
  LIMIT p_limit;

  SELECT COUNT(*) INTO v_selected FROM tmp_rejects;
  RAISE NOTICE 'resolve_price_rejects: selected % candidates (only_unresolved=%)', v_selected, p_only_unresolved;

  --check first if the id is marked as migrated or merged in the migration tables (in case the reject was from a previous run and the dim_price_observation load procedure was fixed in the meantime to populate product_source_id directly)

  -- 1) resolve card_version_id (print_id, external ids, fallback)
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
        AND m.migration_strategy IN ('merge', 'move')   -- add other “redirect” strategies you store
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

  -- 1b) Back-fill mtgstock_id mapping for rows resolved via EXTERNAL_ID or
  --     SET_COLLECTOR (PRINT_ID rows are already in card_external_identifier).
  --     Mirrors the equivalent block in load_staging_prices_batched.
  WITH resolved_prints AS (
    SELECT DISTINCT
      r.print_id,
      r.card_version_id
    FROM tmp_resolved r
    WHERE r.card_version_id IS NOT NULL
      AND r.resolution_method <> 'PRINT_ID'
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
  -- choose at most one print_id per card_version_id to avoid PK conflicts
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
  SELECT
    r.card_identifier_ref_id,
    p.card_version_id,
    p.print_value
  FROM pick_one_per_cv p
  CROSS JOIN mtgstock_ref r
  LEFT JOIN card_catalog.card_external_identifier existing_pk
    ON existing_pk.card_version_id = p.card_version_id
   AND existing_pk.card_identifier_ref_id = r.card_identifier_ref_id
  WHERE existing_pk.card_version_id IS NULL
  ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING;

  -- 2) ensure product_ref + mtg_card_products for newly resolved card_version_id
  WITH need AS (
    SELECT DISTINCT card_version_id
    FROM tmp_resolved
    WHERE card_version_id IS NOT NULL
    EXCEPT
    SELECT card_version_id FROM pricing.mtg_card_products
  ),
  gen AS (
    SELECT card_version_id, uuid_generate_v4() AS product_id
    FROM need
  ),
  ins_prod AS (
    INSERT INTO pricing.product_ref (product_id, game_id)
    SELECT product_id, v_mtg_game_id
    FROM gen
    ON CONFLICT (product_id) DO NOTHING
  )
  INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
  SELECT product_id, card_version_id
  FROM gen
  ON CONFLICT (card_version_id) DO NOTHING;

  -- 3) ensure source_product
  INSERT INTO pricing.source_product (product_id, source_id)
  SELECT DISTINCT mcp.product_id, v_source_id
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  LEFT JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
  WHERE r.card_version_id IS NOT NULL
    AND sp.source_product_id IS NULL
  ON CONFLICT (product_id, source_id) DO NOTHING;

  -- 4) re-feed resolved rejects into stg_price_observation (wide model).
  --    ts_date / data_provider_id are NOT NULL on staging; product_id is UUID.
  --    list_count / sold_count do not exist on staging (they are fact-only).
  --    Rows where all three cents columns are NULL are skipped to match the
  --    downstream procedure's filter and avoid orphan no-op staging rows.
  INSERT INTO pricing.stg_price_observation (
    ts_date, game_code, print_id,
    list_low_cents, list_avg_cents, sold_avg_cents,
    is_foil, source_code, data_provider_id, value,
    product_id, card_version_id, source_product_id,
    set_abbr, collector_number, card_name, scryfall_id, tcg_id,
    scraped_at
  )
  SELECT
    r.ts_date,
    r.game_code,
    r.print_id,
    r.list_low_cents,
    r.list_avg_cents,
    r.sold_avg_cents,
    r.is_foil,
    r.source_code,
    r.data_provider_id,
    r.value,
    mcp.product_id,
    r.card_version_id,
    sp.source_product_id,
    r.set_abbr,
    r.collector_number,
    r.card_name,
    r.scryfall_id,
    r.tcg_id,
    r.scraped_at
  FROM tmp_resolved r
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
  WHERE r.card_version_id IS NOT NULL
    AND NOT (r.list_low_cents IS NULL
         AND r.list_avg_cents IS NULL
         AND r.sold_avg_cents IS NULL);

  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  RAISE NOTICE 'resolve_price_rejects: re-fed % rows into stg_price_observation', v_inserted;

  -- 5) mark resolved rejects as terminal. Natural match key in the wide
  --    model: (ts_date, print_id, is_foil, source_code, data_provider_id,
  --    scraped_at) — one reject row per scrape per (day, product, foil,
  --    provider). If that is not unique in your data, add a surrogate PK
  --    on stg_price_observation_reject.
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
  JOIN pricing.mtg_card_products mcp
    ON mcp.card_version_id = r.card_version_id
  JOIN pricing.source_product sp
    ON sp.product_id = mcp.product_id
   AND sp.source_id = v_source_id
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