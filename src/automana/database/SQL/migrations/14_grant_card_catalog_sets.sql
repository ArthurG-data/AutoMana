-- ============================================================
--  Migration 14: Re-apply grants on card_catalog schema
--
--  Why this is needed
--  ──────────────────
--  card_catalog.sets (and potentially other tables added after
--  migration 13) were created after the last GRANT ... ON ALL TABLES
--  window. ALTER DEFAULT PRIVILEGES covers future tables only —
--  tables that already existed at the time of the previous migration
--  run are not retroactively covered.
--
--  Symptom: app_celery gets "permission denied for table sets"
--  (error code 42501) during Scryfall pipeline card inserts.
--
--  This migration is idempotent: GRANT is a no-op if the privilege
--  is already held. Must be run as automana_admin (or a superuser).
-- ============================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA card_catalog TO app_rw;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA card_catalog TO app_rw;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_rw;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA card_catalog TO app_admin;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA card_catalog TO app_admin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_admin;

GRANT SELECT ON ALL TABLES IN SCHEMA card_catalog TO app_ro, agent_reader;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_ro, agent_reader;

-- Refresh DEFAULT PRIVILEGES so all future tables are covered automatically
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO app_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT SELECT ON TABLES TO app_ro, agent_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_admin, app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT EXECUTE ON FUNCTIONS TO app_admin, app_rw, app_ro, agent_reader;
