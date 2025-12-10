-- Migration Script: Move Shopify staging tables to pricing schema
-- Date: 2025-12-10
-- Description: Migrates Shopify staging tables and procedures to pricing schema

BEGIN;

-- ============================================================================
-- Note: pricing schema should already exist from previous migration
-- ============================================================================

-- ============================================================================
-- PHASE 1: Migrate Staging Tables
-- ============================================================================

DO $$
BEGIN
    -- Migrate shopify_staging_raw
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' AND table_name = 'shopify_staging_raw') THEN
        ALTER TABLE public.shopify_staging_raw SET SCHEMA pricing;
        RAISE NOTICE 'Migrated shopify_staging_raw to pricing schema';
    ELSE
        RAISE NOTICE 'shopify_staging_raw table not found in public schema';
    END IF;

    -- Migrate price_observation_stage
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' AND table_name = 'price_observation_stage') THEN
        ALTER TABLE public.price_observation_stage SET SCHEMA pricing;
        RAISE NOTICE 'Migrated price_observation_stage to pricing schema';
    ELSE
        RAISE NOTICE 'price_observation_stage table not found in public schema';
    END IF;

    -- Migrate market_collection if it exists
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' AND table_name = 'market_collection') THEN
        ALTER TABLE public.market_collection SET SCHEMA pricing;
        RAISE NOTICE 'Migrated market_collection to pricing schema';
    ELSE
        RAISE NOTICE 'market_collection table not found in public schema';
    END IF;
END $$;

-- ============================================================================
-- PHASE 2: Migrate Procedures
-- ============================================================================

DO $$
BEGIN
    -- Migrate raw_to_stage procedure
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid 
               WHERE n.nspname = 'public' AND p.proname = 'raw_to_stage') THEN
        ALTER PROCEDURE public.raw_to_stage() SET SCHEMA pricing;
        RAISE NOTICE 'Migrated raw_to_stage to pricing schema';
    ELSE
        RAISE NOTICE 'raw_to_stage procedure not found in public schema';
    END IF;

    -- Migrate stage_to_price_observation procedure
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid 
               WHERE n.nspname = 'public' AND p.proname = 'stage_to_price_observation') THEN
        ALTER PROCEDURE public.stage_to_price_observation() SET SCHEMA pricing;
        RAISE NOTICE 'Migrated stage_to_price_observation to pricing schema';
    ELSE
        RAISE NOTICE 'stage_to_price_observation procedure not found in public schema';
    END IF;
END $$;

-- ============================================================================
-- PHASE 3: Migrate Functions
-- ============================================================================

-- ============================================================================
-- PHASE 4: Recreate Indexes in pricing schema
-- ============================================================================

DO $$
BEGIN
    -- Indexes are automatically moved with tables, but verify they exist
    
    IF EXISTS (SELECT 1 FROM pg_indexes 
               WHERE schemaname = 'pricing' AND tablename = 'shopify_staging_raw') THEN
        CREATE INDEX IF NOT EXISTS idx_shopify_staging_raw_product_id 
            ON pricing.shopify_staging_raw(product_id);
        CREATE INDEX IF NOT EXISTS idx_shopify_staging_raw_date 
            ON pricing.shopify_staging_raw(date);
        RAISE NOTICE 'Ensured indexes exist on shopify_staging_raw';
    END IF;
END $$;

-- ============================================================================
-- PHASE 5: Summary
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Shopify Staging Migration Complete!';
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Tables migrated to pricing schema:';
    RAISE NOTICE '  - shopify_staging_raw';
    RAISE NOTICE '  - price_observation_stage';
    RAISE NOTICE '  - market_collection (if exists)';
    RAISE NOTICE '';
    RAISE NOTICE 'Procedures migrated:';
    RAISE NOTICE '  - raw_to_stage';
    RAISE NOTICE '  - stage_to_price_observation';
    RAISE NOTICE '';

    RAISE NOTICE '';
    RAISE NOTICE 'Verify with: SELECT * FROM information_schema.tables WHERE table_schema = ''pricing'' AND table_name LIKE ''%%%%staging%%%%'';';
END $$;

COMMIT;

-- Verification Query (uncomment to run)
SELECT table_schema, table_name, table_type
FROM information_schema.tables 
WHERE table_schema = 'pricing'
 ORDER BY table_name;