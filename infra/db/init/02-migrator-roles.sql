/* ============================================================
   Migrator roles: DDL allowed (for Alembic), NOT superuser.
   These roles should be used ONLY by the migration job.
   ============================================================ */

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'migrator_dev') THEN
    CREATE ROLE migrator_dev LOGIN PASSWORD 'CHANGE_ME_MIGRATOR_DEV'
      NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'migrator_test') THEN
    CREATE ROLE migrator_test LOGIN PASSWORD 'CHANGE_ME_MIGRATOR_TEST'
      NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'migrator_prod') THEN
    CREATE ROLE migrator_prod LOGIN PASSWORD 'CHANGE_ME_MIGRATOR_PROD'
      NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
  END IF;
END$$;

-- Ensure app roles exist (in case file order changes)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_dev')  THEN CREATE ROLE app_dev  LOGIN PASSWORD 'CHANGE_ME_DEV'  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_test') THEN CREATE ROLE app_test LOGIN PASSWORD 'CHANGE_ME_TEST' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_prod') THEN CREATE ROLE app_prod LOGIN PASSWORD 'CHANGE_ME_PROD' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
END$$;

-- ========= Multi-schema grants =========
-- Add/extend schemas here as your project grows.
-- (Keep public if you use extensions there.)
DO $$
DECLARE
  s text;
  schemas text[] := ARRAY['public','card_catalog','pricing','auth'];
BEGIN
  FOREACH s IN ARRAY schemas LOOP
    CREATE SCHEMA IF NOT EXISTS s;
    -- Schema must exist before granting; this is safe even if it doesn't.
    EXECUTE format('GRANT USAGE, CREATE ON SCHEMA %I TO migrator_dev, migrator_test, migrator_prod;', s);

    -- Runtime app roles: USAGE only (no CREATE)
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_dev, app_test, app_prod;', s);

    -- Existing objects: app roles get DML
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO app_dev, app_test, app_prod;', s);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO app_dev, app_test, app_prod;', s);

    -- Default privileges for objects CREATED BY migrator roles:
    -- This is critical so new tables created by migrations are immediately usable by the app roles.
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE migrator_dev  IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_dev;',  s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE migrator_dev  IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO app_dev;', s);

    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE migrator_test IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_test;', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE migrator_test IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO app_test;', s);

    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE migrator_prod IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_prod;', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE migrator_prod IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO app_prod;', s);
  END LOOP;
END$$;