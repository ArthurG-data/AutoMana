-- ============================================================
--  Automana RBAC / Grants bootstrap
--
--  Role hierarchy
--  ──────────────
--  db_owner        (NOLOGIN) — owns all schema objects; the only role
--                              that may CREATE / DROP / ALTER tables.
--                              Granted to automana_admin for migration work.
--
--  app_admin       (NOLOGIN) — full DML on every table/sequence/function
--                              across all schemas, but does NOT own objects
--                              → cannot DROP or ALTER tables.
--                              Granted to automana_admin for day-to-day use.
--
--  app_rw          (NOLOGIN) — SELECT + INSERT + UPDATE + DELETE.
--                              Used by app_backend and app_celery.
--
--  app_ro          (NOLOGIN) — SELECT only. Used by app_readonly.
--
--  agent_reader    (NOLOGIN) — SELECT only (subset of schemas in prod).
--
--  Login users
--  ───────────
--  automana_admin  → member of db_owner + app_admin  (migration runner)
--  app_backend     → member of app_rw
--  app_celery      → member of app_rw
--  app_readonly    → member of app_ro
--  app_agent       → member of agent_reader
-- ============================================================

SELECT set_config('automana.admin_pw',    :'admin_pw',    false);
SELECT set_config('automana.backend_pw',  :'backend_pw',  false);
SELECT set_config('automana.celery_pw',   :'celery_pw',   false);
SELECT set_config('automana.agent_pw',    :'agent_pw',    false);
SELECT set_config('automana.readonly_pw', :'readonly_pw', false);

DO $$
DECLARE
  admin_pw    text := current_setting('automana.admin_pw');
  backend_pw  text := current_setting('automana.backend_pw');
  celery_pw   text := current_setting('automana.celery_pw');
  agent_pw    text := current_setting('automana.agent_pw');
  readonly_pw text := current_setting('automana.readonly_pw');

  env text := current_database();
  s   text;

  schemas text[] := ARRAY[
    'card_catalog',
    'user_management',
    'user_collection',
    'app_integration',
    'pricing',
    'markets',
    'ops'
  ];
BEGIN

  -- ----------------------------------------------------------------
  -- Group roles
  -- ----------------------------------------------------------------

  -- db_owner: DDL role — owns all objects, may CREATE/DROP/ALTER.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='db_owner') THEN
    CREATE ROLE db_owner NOLOGIN;
  END IF;

  -- app_admin: full DML everywhere, no DDL (does not own objects).
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_admin') THEN
    CREATE ROLE app_admin NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_rw') THEN
    CREATE ROLE app_rw NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_ro') THEN
    CREATE ROLE app_ro NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agent_reader') THEN
    CREATE ROLE agent_reader NOLOGIN;
  END IF;

  -- ----------------------------------------------------------------
  -- Login users
  -- ----------------------------------------------------------------

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='automana_admin') THEN
    EXECUTE format('CREATE USER automana_admin PASSWORD %L', admin_pw);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_backend') THEN
    EXECUTE format('CREATE USER app_backend PASSWORD %L', backend_pw);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_celery') THEN
    EXECUTE format('CREATE USER app_celery PASSWORD %L', celery_pw);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_readonly') THEN
    EXECUTE format('CREATE USER app_readonly PASSWORD %L', readonly_pw);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_agent') THEN
    EXECUTE format('CREATE USER app_agent PASSWORD %L', agent_pw);
  END IF;

  -- ----------------------------------------------------------------
  -- Membership wiring
  -- ----------------------------------------------------------------

  -- automana_admin: migration runner — needs db_owner for DDL and
  -- app_admin so it can read/write data during development.
  GRANT db_owner  TO automana_admin;
  GRANT app_admin TO automana_admin;

  -- app_admin inherits read/write (but not ownership)
  GRANT app_rw TO app_admin;
  GRANT app_ro TO app_admin;

  GRANT app_rw TO app_backend, app_celery;
  GRANT app_ro TO app_readonly;
  GRANT agent_reader TO app_agent;

  -- ----------------------------------------------------------------
  -- Public schema lockdown
  -- ----------------------------------------------------------------

  REVOKE ALL ON SCHEMA public FROM PUBLIC;
  GRANT USAGE ON SCHEMA public TO app_rw, app_ro, agent_reader, app_admin;
  REVOKE CREATE ON SCHEMA public FROM PUBLIC, app_rw, app_ro, agent_reader, app_admin;
  -- db_owner may create in public (extensions, sequences)
  GRANT CREATE ON SCHEMA public TO db_owner;

  EXECUTE 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_rw, app_admin';

  -- Future public sequences created by db_owner
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

    -- db_owner may create objects in every schema
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

  -- ----------------------------------------------------------------
  -- Celery: explicit function grant (belt-and-suspenders)
  -- ----------------------------------------------------------------
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='card_catalog') THEN
    EXECUTE 'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_celery';
  END IF;

  -- ----------------------------------------------------------------
  -- Prod overrides
  -- ----------------------------------------------------------------
  IF env LIKE '%prod%' THEN
    REVOKE USAGE ON SCHEMA user_management, user_collection, app_integration, pricing FROM agent_reader;
  END IF;

END $$;

-- ----------------------------------------------------------------
-- Materialized views
--
-- PostgreSQL has no REFRESH privilege. Only the MV owner (db_owner)
-- or a superuser can run REFRESH MATERIALIZED VIEW.
-- automana_admin is a member of db_owner, so it can refresh MVs.
-- app_admin and app_rw get SELECT so they can read MV data.
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
