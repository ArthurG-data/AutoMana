-- ============================================================
--  Re-apply per-schema grants + default privileges.
--
--  Schema-level and object-level grants are per-database, so
--  `DROP DATABASE` (as used by rebuild_dev_db.sh) wipes them.
--  The init template `infra/db/init/02-app-roles.sql.tpl` only
--  runs on volume init — it does not re-run after a DROP/CREATE
--  DATABASE cycle. This script is the grant portion of that
--  template, lifted out so a rebuild can call it directly
--  without needing secrets (no password references here).
--
--  Run as
--  ──────
--  automana_admin (cluster superuser) or any role that owns
--  `db_owner`. Idempotent — `GRANT` is a no-op when the
--  privilege is already held.
-- ============================================================

DO $$
DECLARE
  s text;
  schemas text[] := ARRAY[
    'card_catalog',
    'user_management',
    'user_collection',
    'app_integration',
    'pricing',
    'markets',
    'ops',
    'reporting'
  ];
BEGIN
  -- ----------------------------------------------------------------
  -- Public schema lockdown
  -- ----------------------------------------------------------------
  REVOKE ALL ON SCHEMA public FROM PUBLIC;
  GRANT USAGE ON SCHEMA public TO app_rw, app_ro, agent_reader, app_admin;
  REVOKE CREATE ON SCHEMA public FROM PUBLIC, app_rw, app_ro, agent_reader, app_admin;
  GRANT CREATE ON SCHEMA public TO db_owner;

  EXECUTE 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_rw, app_admin';
  EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA public
           GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw, app_admin';

  BEGIN
    GRANT EXECUTE ON FUNCTION public.uuid_generate_v4() TO app_rw, app_admin;
  EXCEPTION WHEN undefined_function THEN
    NULL;
  END;

  -- ----------------------------------------------------------------
  -- Per-schema grants + default privileges
  -- ----------------------------------------------------------------
  FOREACH s IN ARRAY schemas LOOP
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION db_owner;', s);

    -- Schema visibility
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_admin, app_rw, app_ro, agent_reader;', s);
    EXECUTE format('GRANT CREATE ON SCHEMA %I TO db_owner;', s);

    -- app_admin: full DML — no CREATE/DROP (not the owner)
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA %I TO app_admin;', s);
    EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO app_admin;', s);
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_admin;', s);

    -- app_rw: standard read/write (no TRUNCATE)
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO app_rw;', s);
    EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO app_rw;', s);
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_rw;', s);

    -- app_ro / agent_reader: read only
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO app_ro, agent_reader;', s);
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_ro, agent_reader;', s);

    -- Default privileges for future objects created by db_owner
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
       GRANT EXECUTE ON FUNCTIONS TO app_admin, app_rw;', s);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA %I
       GRANT EXECUTE ON FUNCTIONS TO app_ro, agent_reader;', s);
  END LOOP;

  -- Belt-and-suspenders routine grant to app_celery (ALL ROUTINES covers both functions and procedures)
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'card_catalog') THEN
    EXECUTE 'GRANT EXECUTE ON ALL ROUTINES IN SCHEMA card_catalog TO app_celery';
  END IF;

  -- Prod override: revoke agent access to user/billing/app-integration/pricing
  IF current_database() LIKE '%prod%' THEN
    REVOKE USAGE ON SCHEMA user_management, user_collection, app_integration, pricing FROM agent_reader;
  END IF;
END $$;

-- ----------------------------------------------------------------
-- Materialized views need explicit SELECT (no bulk GRANT covers them)
-- ----------------------------------------------------------------
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT schemaname, matviewname
    FROM pg_matviews
    WHERE schemaname IN (
      'card_catalog','user_management','user_collection',
      'app_integration','pricing','markets','ops'
    )
  LOOP
    EXECUTE format(
      'GRANT SELECT ON %I.%I TO app_admin, app_rw, app_ro, agent_reader;',
      r.schemaname, r.matviewname
    );
  END LOOP;
END $$;
