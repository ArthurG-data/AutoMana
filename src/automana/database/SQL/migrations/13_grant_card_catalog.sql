-- ============================================================
--  Migration 13: Re-apply grants on card_catalog schema
--
--  Why this is needed
--  ──────────────────
--  Migration 10 issued GRANT ... ON ALL TABLES IN SCHEMA for each
--  schema at that point in time. If any card_catalog tables were
--  created in a fresh environment before db_owner / app_admin
--  existed, or if the bootstrap order ran 01_set_schema.sql after
--  migration 10's DEFAULT PRIVILEGES window, those tables have no
--  grants for app_admin or app_rw.
--
--  This migration is idempotent: GRANT is a no-op if the privilege
--  is already held.
--
--  Must be run as automana_admin (or a superuser).
-- ============================================================

DO $$
DECLARE
  s TEXT;
  schemas TEXT[] := ARRAY[
    'card_catalog',
    'user_management',
    'user_collection',
    'app_integration',
    'pricing',
    'markets',
    'ops'
  ];
BEGIN
  FOREACH s IN ARRAY schemas LOOP

    -- Ensure schema visibility
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_admin, app_rw, app_ro, agent_reader;', s);

    -- app_admin: full DML on all current tables
    EXECUTE format(
      'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA %I TO app_admin;', s);
    EXECUTE format(
      'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO app_admin;', s);
    EXECUTE format(
      'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_admin;', s);

    -- app_rw: standard read/write on all current tables
    EXECUTE format(
      'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO app_rw;', s);
    EXECUTE format(
      'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO app_rw;', s);
    EXECUTE format(
      'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_rw;', s);

    -- app_ro / agent_reader: read only
    EXECUTE format(
      'GRANT SELECT ON ALL TABLES IN SCHEMA %I TO app_ro, agent_reader;', s);
    EXECUTE format(
      'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_ro, agent_reader;', s);

    -- Refresh DEFAULT PRIVILEGES so future tables are covered automatically
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA %I
       GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO app_admin;', s);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA %I
       GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;', s);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA %I
       GRANT SELECT ON TABLES TO app_ro, agent_reader;', s);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA %I
       GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_admin, app_rw;', s);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA %I
       GRANT EXECUTE ON FUNCTIONS TO app_admin, app_rw, app_ro, agent_reader;', s);

    RAISE NOTICE 'Grants re-applied for schema: %', s;
  END LOOP;
END $$;
