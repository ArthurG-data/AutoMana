-- Migration Script: Move pricing schema tables from public to pricing
-- Date: 2025-12-10
-- Description: Migrates price-related tables and TimescaleDB hypertables to pricing schema

BEGIN;

-- ============================================================================
-- PHASE 1: Create pricing schema
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS pricing;

-- ============================================================================
-- PHASE 2: Migrate Reference Tables
-- ============================================================================

DO $$
BEGIN
    -- Migrate price_source
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'price_source') THEN
        ALTER TABLE public.price_source SET SCHEMA pricing;
        RAISE NOTICE 'Migrated price_source to pricing schema';
    END IF;

    -- Migrate price_metric
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'price_metric') THEN
        ALTER TABLE public.price_metric SET SCHEMA pricing;
        RAISE NOTICE 'Migrated price_metric to pricing schema';
    END IF;

    -- Migrate card_condition
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'card_condition') THEN
        ALTER TABLE public.card_condition SET SCHEMA pricing;
        RAISE NOTICE 'Migrated card_condition to pricing schema';
    END IF;

    -- Migrate card_finished (rename to card_finish)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'card_finished') THEN
        ALTER TABLE public.card_finished RENAME TO card_finish;
        ALTER TABLE public.card_finish SET SCHEMA pricing;
        RAISE NOTICE 'Renamed card_finished to card_finish and migrated to pricing schema';
    ELSIF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'card_finish') THEN
        ALTER TABLE public.card_finish SET SCHEMA pricing;
        RAISE NOTICE 'Migrated card_finish to pricing schema';
    END IF;

    -- Migrate card_game
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'card_game') THEN
        ALTER TABLE public.card_game SET SCHEMA pricing;
        RAISE NOTICE 'Migrated card_game to pricing schema';
    END IF;
END $$;

-- ============================================================================
-- PHASE 3: Migrate Staging Tables
-- ============================================================================

DO $$
BEGIN
    -- Migrate raw_mtg_stock_price
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'raw_mtg_stock_price') THEN
        ALTER TABLE public.raw_mtg_stock_price SET SCHEMA pricing;
        RAISE NOTICE 'Migrated raw_mtg_stock_price to pricing schema';
    END IF;

    -- Migrate stg_price_observation
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'stg_price_observation') THEN
        ALTER TABLE public.stg_price_observation SET SCHEMA pricing;
        RAISE NOTICE 'Migrated stg_price_observation to pricing schema';
    END IF;

    -- Migrate dim_price_observation
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'dim_price_observation') THEN
        ALTER TABLE public.dim_price_observation SET SCHEMA pricing;
        RAISE NOTICE 'Migrated dim_price_observation to pricing schema';
    END IF;
END $$;

-- ============================================================================
-- PHASE 4: Migrate Hypertable (Special Handling for TimescaleDB)
-- ============================================================================

DO $$
BEGIN
    -- For hypertables, we need to use a different approach
    -- TimescaleDB hypertables can be moved but require special care
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'price_observation') THEN
        -- Check if it's a hypertable using correct column names
        IF EXISTS (SELECT 1 FROM timescaledb_information.hypertables 
                   WHERE hypertable_schema = 'public' AND hypertable_name = 'price_observation') THEN
            RAISE NOTICE 'price_observation is a hypertable - moving with special care';
            -- Move hypertable and all its chunks
            ALTER TABLE public.price_observation SET SCHEMA pricing;
            RAISE NOTICE 'Migrated hypertable price_observation to pricing schema';
        ELSE
            -- Regular table
            ALTER TABLE public.price_observation SET SCHEMA pricing;
            RAISE NOTICE 'Migrated price_observation to pricing schema';
        END IF;
    ELSE
        RAISE NOTICE 'price_observation table not found in public schema';
    END IF;
END $$;

-- ============================================================================
-- PHASE 5: Migrate/Rename Views
-- ============================================================================

DO $$
BEGIN
    -- Migrate and rename price_weekly to v_price_weekly (Continuous Aggregate)
    IF EXISTS (SELECT 1 FROM timescaledb_information.continuous_aggregates 
               WHERE view_schema = 'public' AND view_name = 'price_weekly') THEN
        ALTER MATERIALIZED VIEW public.price_weekly RENAME TO v_price_weekly;
        ALTER MATERIALIZED VIEW public.v_price_weekly SET SCHEMA pricing;
        RAISE NOTICE 'Renamed price_weekly to v_price_weekly and migrated to pricing schema';
    ELSIF EXISTS (SELECT 1 FROM timescaledb_information.continuous_aggregates 
                  WHERE view_schema = 'pricing' AND view_name = 'price_weekly') THEN
        ALTER MATERIALIZED VIEW pricing.price_weekly RENAME TO v_price_weekly;
        RAISE NOTICE 'Renamed price_weekly to v_price_weekly in pricing schema';
    ELSIF EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema = 'public' AND table_name = 'price_weekly') THEN
        -- Regular materialized view (not continuous aggregate)
        ALTER MATERIALIZED VIEW public.price_weekly RENAME TO v_price_weekly;
        ALTER MATERIALIZED VIEW public.v_price_weekly SET SCHEMA pricing;
        RAISE NOTICE 'Renamed price_weekly to v_price_weekly and migrated to pricing schema';
    ELSE
        RAISE NOTICE 'price_weekly view not found, skipping';
    END IF;
END $$;

-- ============================================================================
-- PHASE 6: Migrate Functions/Procedures
-- ============================================================================

DO $$
BEGIN
    -- Migrate load_staging_prices_batched
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid 
               WHERE n.nspname = 'public' AND p.proname = 'load_staging_prices_batched') THEN
        ALTER PROCEDURE public.load_staging_prices_batched(int) SET SCHEMA pricing;
        RAISE NOTICE 'Migrated load_staging_prices_batched to pricing schema';
    ELSE
        RAISE NOTICE 'load_staging_prices_batched procedure not found in public schema';
    END IF;

    -- Migrate load_dim_from_staging
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid 
               WHERE n.nspname = 'public' AND p.proname = 'load_dim_from_staging') THEN
        ALTER PROCEDURE public.load_dim_from_staging() SET SCHEMA pricing;
        RAISE NOTICE 'Migrated load_dim_from_staging to pricing schema';
    ELSE
        RAISE NOTICE 'load_dim_from_staging procedure not found in public schema';
    END IF;

    -- Migrate load_prices_from_dim_batched
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid 
               WHERE n.nspname = 'public' AND p.proname = 'load_prices_from_dim_batched') THEN
        ALTER PROCEDURE public.load_prices_from_dim_batched(int) SET SCHEMA pricing;
        RAISE NOTICE 'Migrated load_prices_from_dim_batched to pricing schema';
    ELSE
        RAISE NOTICE 'load_prices_from_dim_batched procedure not found in public schema';
    END IF;
END $$;

-- ============================================================================
-- PHASE 7: Update Indexes
-- ============================================================================

DO $$
BEGIN
    -- Note: Indexes are automatically moved with their tables
    -- But we can verify/recreate if needed
    
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'pricing' AND tablename = 'dim_price_observation') THEN
        CREATE INDEX IF NOT EXISTS dim_price_obs_ts_idx ON pricing.dim_price_observation (ts_date);
        RAISE NOTICE 'Ensured dim_price_obs_ts_idx exists';
    END IF;
END $$;

-- ============================================================================
-- PHASE 8: Summary
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Migration Complete!';
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Reference Tables migrated to pricing schema:';
    RAISE NOTICE '  - price_source';
    RAISE NOTICE '  - price_metric';
    RAISE NOTICE '  - card_condition';
    RAISE NOTICE '  - card_finish (renamed from card_finished)';
    RAISE NOTICE '  - card_game';
    RAISE NOTICE '';
    RAISE NOTICE 'Staging Tables migrated:';
    RAISE NOTICE '  - raw_mtg_stock_price';
    RAISE NOTICE '  - stg_price_observation';
    RAISE NOTICE '  - dim_price_observation';
    RAISE NOTICE '';
    RAISE NOTICE 'Hypertable migrated:';
    RAISE NOTICE '  - price_observation (with chunks and compression)';
    RAISE NOTICE '';
    RAISE NOTICE 'Views renamed with v_ prefix:';
    RAISE NOTICE '  - v_price_weekly (continuous aggregate)';
    RAISE NOTICE '';
    RAISE NOTICE 'Procedures migrated:';
    RAISE NOTICE '  - load_staging_prices_batched';
    RAISE NOTICE '  - load_dim_from_staging';
    RAISE NOTICE '  - load_prices_from_dim_batched';
    RAISE NOTICE '';
    RAISE NOTICE 'Verify with: SELECT * FROM information_schema.tables WHERE table_schema = ''pricing'';';
END $$;

COMMIT;

-- Verification Queries (uncomment to run)
-- SELECT table_schema, table_name, table_type
-- FROM information_schema.tables 
-- WHERE table_schema = 'pricing'
-- ORDER BY table_type, table_name;

-- SELECT hypertable_schema, hypertable_name
-- FROM timescaledb_information.hypertables
-- WHERE hypertable_schema = 'pricing';