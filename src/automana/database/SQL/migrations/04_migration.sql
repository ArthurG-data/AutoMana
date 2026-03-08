-- Migration Script: Move user_collection schema tables from public to user_collection
-- Date: 2025-12-10
-- Description: Migrates collection-related tables to user_collection schema

BEGIN;

-- ============================================================================
-- PHASE 1: Create user_collection schema
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS user_collection;

-- ============================================================================
-- PHASE 2: Migrate Tables from public to user_collection schema
-- ============================================================================

-- Migrate ref_condition table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND (table_name = 'Ref_Condition' OR table_name = 'ref_condition')) THEN
        
        -- If old capitalized version exists, rename first
        IF EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_schema = 'public' AND table_name = 'Ref_Condition') THEN
            ALTER TABLE public."Ref_Condition" RENAME TO ref_condition;
        END IF;
        
        -- Move to user_collection schema
        ALTER TABLE public.ref_condition SET SCHEMA user_collection;
        RAISE NOTICE 'Migrated ref_condition to user_collection schema';
    ELSE
        RAISE NOTICE 'ref_condition table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate collections table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND (table_name = 'Collections' OR table_name = 'collections')) THEN
        
        -- If old capitalized version exists, rename first
        IF EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_schema = 'public' AND table_name = 'Collections') THEN
            ALTER TABLE public."Collections" RENAME TO collections;
        END IF;
        
        -- Move to user_collection schema
        ALTER TABLE public.collections SET SCHEMA user_collection;
        RAISE NOTICE 'Migrated collections to user_collection schema';
    ELSE
        RAISE NOTICE 'collections table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate collection_items table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND (table_name = 'CollectionItems' OR table_name = 'collection_items')) THEN
        
        -- If old capitalized version exists, rename first
        IF EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_schema = 'public' AND table_name = 'CollectionItems') THEN
            ALTER TABLE public."CollectionItems" RENAME TO collection_items;
        END IF;
        
        -- Move to user_collection schema
        ALTER TABLE public.collection_items SET SCHEMA user_collection;
        RAISE NOTICE 'Migrated collection_items to user_collection schema';
    ELSE
        RAISE NOTICE 'collection_items table not found in public schema, skipping';
    END IF;
END $$;

-- ============================================================================
-- PHASE 3: Summary
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Migration Complete!';
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Tables migrated to user_collection schema:';
    RAISE NOTICE '  - ref_condition';
    RAISE NOTICE '  - collections';
    RAISE NOTICE '  - collection_items';
    RAISE NOTICE '';
    RAISE NOTICE 'Verify with: SELECT * FROM information_schema.tables WHERE table_schema = ''user_collection'';';
END $$;

COMMIT;

-- Verification Query (uncomment to run)
-- SELECT table_schema, table_name 
-- FROM information_schema.tables 
-- WHERE table_schema = 'user_collection'
-- ORDER BY table_name;