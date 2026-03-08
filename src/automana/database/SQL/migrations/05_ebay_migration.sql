-- Migration Script: Move app_integration schema tables from public to app_integration
-- Date: 2025-12-10
-- Description: Migrates eBay/external app integration tables to app_integration schema

BEGIN;

-- ============================================================================
-- PHASE 1: Create app_integration schema
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS app_integration;

-- ============================================================================
-- PHASE 2: Migrate Tables from public to app_integration schema
-- ============================================================================

-- Migrate app_info table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'app_info') THEN
        
        ALTER TABLE public.app_info SET SCHEMA app_integration;
        RAISE NOTICE 'Migrated app_info to app_integration schema';
    ELSE
        RAISE NOTICE 'app_info table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate app_user table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'app_user') THEN
        
        ALTER TABLE public.app_user SET SCHEMA app_integration;
        RAISE NOTICE 'Migrated app_user to app_integration schema';
    ELSE
        RAISE NOTICE 'app_user table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate ebay_tokens table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'ebay_tokens') THEN
        
        ALTER TABLE public.ebay_tokens SET SCHEMA app_integration;
        RAISE NOTICE 'Migrated ebay_tokens to app_integration schema';
    ELSE
        RAISE NOTICE 'ebay_tokens table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate scopes table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'scopes') THEN
        
        ALTER TABLE public.scopes SET SCHEMA app_integration;
        RAISE NOTICE 'Migrated scopes to app_integration schema';
    ELSE
        RAISE NOTICE 'scopes table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate scope_app table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'scope_app') THEN
        
        ALTER TABLE public.scope_app SET SCHEMA app_integration;
        RAISE NOTICE 'Migrated scope_app to app_integration schema';
    ELSE
        RAISE NOTICE 'scope_app table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate scopes_user table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'scopes_user') THEN
        
        ALTER TABLE public.scopes_user SET SCHEMA app_integration;
        RAISE NOTICE 'Migrated scopes_user to app_integration schema';
    ELSE
        RAISE NOTICE 'scopes_user table not found in public schema, skipping';
    END IF;
END $$;

-- Migrate log_oauth_request table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'log_oauth_request') THEN
        
        ALTER TABLE public.log_oauth_request SET SCHEMA app_integration;
        RAISE NOTICE 'Migrated log_oauth_request to app_integration schema';
    ELSE
        RAISE NOTICE 'log_oauth_request table not found in public schema, skipping';
    END IF;
END $$;

-- ============================================================================
-- PHASE 3: Rename Views to add v_ prefix
-- ============================================================================

-- Rename ebay_app view to v_ebay_app
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.views 
               WHERE table_schema = 'public' 
               AND table_name = 'ebay_app') THEN
        
        ALTER VIEW public.ebay_app RENAME TO v_ebay_app;
        ALTER VIEW public.v_ebay_app SET SCHEMA app_integration;
        RAISE NOTICE 'Renamed and migrated ebay_app to app_integration.v_ebay_app';
    ELSIF EXISTS (SELECT 1 FROM information_schema.views 
                  WHERE table_schema = 'app_integration' 
                  AND table_name = 'ebay_app') THEN
        
        ALTER VIEW app_integration.ebay_app RENAME TO v_ebay_app;
        RAISE NOTICE 'Renamed ebay_app to v_ebay_app in app_integration schema';
    ELSE
        RAISE NOTICE 'ebay_app view not found, skipping';
    END IF;
END $$;

-- ============================================================================
-- PHASE 4: Recreate indexes in new schema
-- ============================================================================

-- Drop old index if exists and recreate in new schema
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_indexes 
               WHERE schemaname = 'public' 
               AND indexname = 'idx_oauth_session') THEN
        
        DROP INDEX public.idx_oauth_session;
        RAISE NOTICE 'Dropped old idx_oauth_session from public schema';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes 
                   WHERE schemaname = 'app_integration' 
                   AND indexname = 'idx_oauth_session') THEN
        
        -- Note: This will fail if session_id column doesn't exist
        -- The original file has this index but no session_id column
        -- You may need to comment this out or fix the column reference
        -- CREATE INDEX idx_oauth_session ON app_integration.log_oauth_request(session_id);
        RAISE NOTICE 'Skipped idx_oauth_session creation - verify column exists';
    END IF;
END $$;

-- ============================================================================
-- PHASE 5: Summary
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Migration Complete!';
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Tables migrated to app_integration schema:';
    RAISE NOTICE '  - app_info';
    RAISE NOTICE '  - app_user';
    RAISE NOTICE '  - ebay_tokens';
    RAISE NOTICE '  - scopes';
    RAISE NOTICE '  - scope_app';
    RAISE NOTICE '  - scopes_user';
    RAISE NOTICE '  - log_oauth_request';
    RAISE NOTICE '';
    RAISE NOTICE 'Views renamed with v_ prefix:';
    RAISE NOTICE '  - v_ebay_app';
    RAISE NOTICE '';
    RAISE NOTICE 'Verify with: SELECT * FROM information_schema.tables WHERE table_schema = ''app_integration'';';
END $$;

COMMIT;

-- Verification Query (uncomment to run)
-- SELECT table_schema, table_name, table_type
-- FROM information_schema.tables 
-- WHERE table_schema = 'app_integration'
-- ORDER BY table_type, table_name;