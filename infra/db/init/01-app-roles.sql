/* ============================================================
   Runtime application roles (NO schema changes allowed)
   Environments: dev / test / prod
   ============================================================ */

-- =========================
-- DEV
-- =========================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_dev') THEN
        CREATE ROLE app_dev
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT;
    END IF;
END$$;

-- =========================
-- TEST
-- =========================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_test') THEN
        CREATE ROLE app_test
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT;
    END IF;
END$$;

-- =========================
-- PROD
-- =========================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_prod') THEN
        CREATE ROLE app_prod
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT;
    END IF;
END$$;

-- ============================================================
-- Privileges (apply to CURRENT database only)
-- This file runs once per DB at init time
-- ============================================================

-- Revoke dangerous defaults
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Grant schema usage only (no CREATE)
GRANT USAGE ON SCHEMA public TO app_dev, app_test, app_prod;

-- Allow data access on existing tables
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public
TO app_dev, app_test, app_prod;

-- Allow sequences (serial / identity columns)
GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA public
TO app_dev, app_test, app_prod;

-- Ensure future objects inherit correct permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES
TO app_dev, app_test, app_prod;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT
ON SEQUENCES
TO app_dev, app_test, app_prod;
