-- ============================================================
--  Automana RBAC / Grants bootstrap (dev-friendly, secure-ish)
--  - Creates roles + login users
--  - Creates schemas
--  - Grants USAGE + table/sequence/function privileges
--  - Sets DEFAULT PRIVILEGES for future objects
--  - Fixes "public schema locked" issues for extensions/sequences
--  - Adds REFRESH privilege for materialized views
-- ============================================================

-- Passwords injected via psql variables (as you already do)
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

  -- Add any schemas you use here (include card_catalogue if it ever existed)
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
  -- ----------------------------
  -- Roles (group roles)
  -- ----------------------------
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

  -- ----------------------------
  -- Users (login roles)
  -- ----------------------------
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

  -- Optional: make automana_admin default to app_admin on login (handy in dev)
  -- NOTE: This doesn't change privileges; it changes default role after login.
  ALTER ROLE automana_admin SET ROLE app_admin;

  -- ----------------------------
  -- Membership wiring
  -- ----------------------------
  GRANT app_admin TO automana_admin;

  GRANT app_rw TO app_backend, app_celery;
  GRANT app_ro TO app_readonly;
  GRANT agent_reader TO app_agent;

  -- app_admin also has rw+ro
  GRANT app_rw TO app_admin;
  GRANT app_ro TO app_admin;

  -- ----------------------------
  -- Lock down public schema, but keep what's necessary
  -- ----------------------------
  -- Remove default public privileges (good)
  REVOKE ALL ON SCHEMA public FROM PUBLIC;

  -- BUT: allow app roles to *use* public objects (extensions, sequences that ended up there)
  -- This prevents: "permission denied for schema public" and missing uuid_generate_v4()
  GRANT USAGE ON SCHEMA public TO app_rw, app_ro, agent_reader;

  -- If uuid-ossp is installed, make it callable (ignore if not installed)
  -- (can't IF EXISTS on GRANT easily; safest to attempt via EXECUTE and ignore failure)
  BEGIN
    GRANT EXECUTE ON FUNCTION public.uuid_generate_v4() TO app_rw;
  EXCEPTION WHEN undefined_function THEN
    -- ok (maybe you use pgcrypto instead)
    NULL;
  END;

  -- Ensure sequences in public are usable by app_rw (fixes your "sequence in public" issue)
  -- (covers legacy sequences that accidentally landed in public)
  EXECUTE 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_rw';

  -- Future public sequences created by automana_admin should also be usable
  EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA public
           GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw';

  -- Prevent object creation in public by normal roles (keeps it clean)
  REVOKE CREATE ON SCHEMA public FROM PUBLIC;
  REVOKE CREATE ON SCHEMA public FROM app_rw, app_ro, agent_reader;

  -- ----------------------------
  -- Schemas + base grants + defaults
  -- ----------------------------
  FOREACH s IN ARRAY schemas LOOP
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I;', s);

    -- Schema visibility
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_rw, app_ro, agent_reader;', s);

    -- Tables (existing)
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO app_rw;', s);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO app_ro, agent_reader;', s);

    -- Sequences (existing)
    EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO app_rw;', s);

    -- Functions (existing)
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_rw;', s);
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_ro, agent_reader;', s);

    -- Allow admin role to create objects in schema
    EXECUTE format('GRANT CREATE ON SCHEMA %I TO app_admin;', s);

    -- Default privileges for *future* objects created by automana_admin in this schema
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
       GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;', s
    );
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
       GRANT SELECT ON TABLES TO app_ro;', s
    );
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
       GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw;', s
    );
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
       GRANT EXECUTE ON FUNCTIONS TO app_rw;', s
    );
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
       GRANT EXECUTE ON FUNCTIONS TO app_ro, agent_reader;', s
    );

    -- Materialized views: SELECT is covered by TABLES grants, but REFRESH is separate.
    -- We'll grant schema-wide REFRESH to app_rw after objects exist (done below).
  END LOOP;

  -- ----------------------------
  -- Celery specifics
  -- ----------------------------
  -- Celery usually needs execute on ingestion functions; app_rw already covers it,
  -- but keep your explicit grant for readability (no harm).
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='card_catalog') THEN
    EXECUTE 'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_celery';
  END IF;

  -- ----------------------------
  -- ENV-specific overrides
  -- ----------------------------
  IF env LIKE '%prod%' THEN
    REVOKE USAGE ON SCHEMA user_management, user_collection, app_integration, pricing FROM agent_reader;
  END IF;

END $$;

-- ------------------------------------------------------------
-- Post-step: grant REFRESH on any existing materialized views
-- (Must run after MVs exist; safe to re-run)
-- ------------------------------------------------------------
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT schemaname, matviewname
    FROM pg_matviews
    WHERE schemaname IN ('card_catalog','user_management','user_collection','app_integration','pricing','markets','ops')
  LOOP
    EXECUTE format('GRANT REFRESH ON MATERIALIZED VIEW %I.%I TO app_rw;', r.schemaname, r.matviewname);
  END LOOP;
END $$;
