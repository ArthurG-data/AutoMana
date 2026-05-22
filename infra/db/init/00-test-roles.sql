-- Minimal role bootstrap for integration test containers.
-- Production role creation (with hashed passwords) is handled by 01-app-roles.sh.
-- This file creates the group roles and login stubs that schema files reference.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'db_owner') THEN
    CREATE ROLE db_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_admin') THEN
    CREATE ROLE app_admin NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
    CREATE ROLE app_rw NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_ro') THEN
    CREATE ROLE app_ro NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') THEN
    CREATE ROLE agent_reader NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'automana_admin') THEN
    CREATE ROLE automana_admin LOGIN PASSWORD 'test_password';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
    CREATE ROLE app_backend LOGIN PASSWORD 'test_password';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_celery') THEN
    CREATE ROLE app_celery LOGIN PASSWORD 'test_password';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_readonly') THEN
    CREATE ROLE app_readonly LOGIN PASSWORD 'test_password';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_agent') THEN
    CREATE ROLE app_agent LOGIN PASSWORD 'test_password';
  END IF;

  GRANT db_owner  TO automana_admin;
  GRANT app_admin TO automana_admin;
  GRANT app_rw    TO app_admin;
  GRANT app_ro    TO app_admin;
  GRANT app_rw    TO app_backend, app_celery;
  GRANT app_ro    TO app_readonly;
  GRANT agent_reader TO app_agent;
END $$;
