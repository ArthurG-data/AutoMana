-- ============================================================
--  Maintenance: flip `app_admin` ↔ `automana_admin` privileges
--  on an already-initialised cluster.
--
--  Why
--  ───
--  The dev compose used to set `POSTGRES_USER=app_admin`, so the
--  postgres image's initdb created `app_admin` as the cluster
--  superuser. The `02-app-roles.sql.tpl` template that ran later
--  tried to `CREATE ROLE app_admin NOLOGIN` but its `IF NOT EXISTS`
--  guard no-op'd, leaving `app_admin` a LOGIN superuser forever —
--  exactly what the role design is trying to prevent.
--
--  Once `docker-compose.dev.yml` is updated to use
--  `POSTGRES_USER=automana_admin`, fresh volumes come up correctly.
--  This script repairs an existing volume without a wipe.
--
--  What this does
--  ──────────────
--  1. Ensures `automana_admin` exists with LOGIN + SUPERUSER so it
--     can act as the bootstrap user going forward.
--  2. Strips every superuser / CREATEDB / CREATEROLE / REPLICATION
--     / LOGIN bit off `app_admin`, returning it to the NOLOGIN
--     group role the design specifies.
--  3. Makes sure `automana_admin` is a member of `db_owner` +
--     `app_admin` per 02-app-roles.sql.tpl.
--
--  Run as
--  ──────
--  A cluster superuser — today that is `app_admin` itself (before
--  the demote). Pipe this file through psql logged in as app_admin
--  ONE LAST TIME. After commit, app_admin can no longer log in.
--
--  After running
--  ─────────────
--  - Restart the postgres container (or wait for the existing
--    healthcheck to flip once you patch compose to use the new
--    user — already done in the tracked file).
--  - Rebuild-script default superuser is now `automana_admin`
--    (already reverted in rebuild_dev_db.sh).
-- ============================================================

BEGIN;

-- Safety: abort if automana_admin doesn't exist. The template normally
-- creates it, but if the init never ran we'd silently lock ourselves
-- out of the cluster.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'automana_admin') THEN
    RAISE EXCEPTION
      'automana_admin role does not exist. Run infra/db/init/02-app-roles.sql.tpl first.';
  END IF;
END $$;

-- 1. Promote automana_admin to superuser. Keep all other attributes
--    as-is (it already has LOGIN + a password from the init template).
ALTER ROLE automana_admin WITH SUPERUSER CREATEDB CREATEROLE REPLICATION;

-- 2. Ensure membership wiring matches the design even if the init
--    template ran in a different order or skipped a grant.
GRANT db_owner  TO automana_admin;
GRANT app_admin TO automana_admin;

-- 3. Demote app_admin back to a pure NOLOGIN group role.
--    Doing this last ensures automana_admin has already inherited
--    everything it needs before app_admin loses its login bit.
ALTER ROLE app_admin WITH
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOREPLICATION
  NOLOGIN;

-- 4. Sanity check — fail the transaction if either role didn't land
--    in the expected state.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'automana_admin' AND rolsuper AND rolcanlogin
  ) THEN
    RAISE EXCEPTION 'automana_admin is not SUPERUSER+LOGIN after the flip.';
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'app_admin'
      AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolcanlogin)
  ) THEN
    RAISE EXCEPTION 'app_admin still has elevated privileges after the flip.';
  END IF;

  RAISE NOTICE 'Role flip successful — app_admin is now NOLOGIN, automana_admin is the cluster superuser.';
END $$;

COMMIT;
