-- ============================================================
--  Migration 10: Introduce db_owner, restrict app_admin to DML
--
--  What this does
--  ──────────────
--  1. Creates the db_owner group role (owns all schema objects).
--  2. Transfers ownership of all existing schemas, tables,
--     sequences, and functions from automana_admin → db_owner.
--  3. Grants db_owner membership to automana_admin so it can
--     still run future migrations.
--  4. Ensures app_admin has SELECT/INSERT/UPDATE/DELETE/TRUNCATE
--     on all tables but is NOT an object owner → cannot DROP.
--  5. Updates DEFAULT PRIVILEGES so future objects created by
--     db_owner automatically inherit the same grants.
--
--  Must be run as a superuser (e.g. postgres) or as automana_admin
--  before ownership is transferred.
--
--  Safe to re-run (all statements are idempotent).
-- ============================================================

-- ----------------------------------------------------------------
-- 1. Create db_owner role if it does not exist
-- ----------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'db_owner') THEN
    CREATE ROLE db_owner NOLOGIN;
    RAISE NOTICE 'Created role db_owner';
  ELSE
    RAISE NOTICE 'Role db_owner already exists — skipping CREATE';
  END IF;
END $$;

-- ----------------------------------------------------------------
-- 2. Grant db_owner to automana_admin
--    (required before REASSIGN OWNED can hand objects to db_owner)
-- ----------------------------------------------------------------
GRANT db_owner TO automana_admin;

-- ----------------------------------------------------------------
-- 3. Transfer all objects owned by automana_admin to db_owner
--
--    REASSIGN OWNED moves: tables, sequences, functions, schemas,
--    types, etc. — everything automana_admin created.
--    Must be run while connected as a superuser.
-- ----------------------------------------------------------------
REASSIGN OWNED BY automana_admin TO db_owner;

-- ----------------------------------------------------------------
-- 4. Schema-level ownership + visibility
-- ----------------------------------------------------------------
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
    'ops'
  ];
BEGIN
  FOREACH s IN ARRAY schemas LOOP

    -- db_owner is now the schema owner; also allow CREATE for DDL work
    EXECUTE format('ALTER SCHEMA %I OWNER TO db_owner;', s);
    EXECUTE format('GRANT CREATE ON SCHEMA %I TO db_owner;', s);

    -- All application roles need USAGE to see objects
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_admin, app_rw, app_ro, agent_reader;', s);

    -- ── app_admin: full DML, no DDL ──────────────────────────────
    -- Not the owner → cannot DROP or ALTER any object.
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
                    ON ALL TABLES IN SCHEMA %I TO app_admin;', s);
    EXECUTE format('GRANT USAGE, SELECT, UPDATE
                    ON ALL SEQUENCES IN SCHEMA %I TO app_admin;', s);
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_admin;', s);

    -- ── app_rw: standard read/write ──────────────────────────────
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE
                    ON ALL TABLES IN SCHEMA %I TO app_rw;', s);
    EXECUTE format('GRANT USAGE, SELECT, UPDATE
                    ON ALL SEQUENCES IN SCHEMA %I TO app_rw;', s);
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_rw;', s);

    -- ── app_ro / agent_reader: read only ─────────────────────────
    EXECUTE format('GRANT SELECT ON ALL TABLES    IN SCHEMA %I TO app_ro, agent_reader;', s);
    EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO app_ro, agent_reader;', s);

    -- ── Default privileges for future objects by db_owner ────────
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

    RAISE NOTICE 'Grants applied for schema: %', s;
  END LOOP;
END $$;

-- ----------------------------------------------------------------
-- 5. Public schema
-- ----------------------------------------------------------------
REVOKE CREATE ON SCHEMA public FROM PUBLIC, app_rw, app_ro, agent_reader, app_admin;
GRANT  CREATE ON SCHEMA public TO db_owner;
GRANT  USAGE  ON SCHEMA public TO app_admin, app_rw, app_ro, agent_reader;

GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_admin, app_rw;

ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_admin, app_rw;

-- ----------------------------------------------------------------
-- 6. Materialized views
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