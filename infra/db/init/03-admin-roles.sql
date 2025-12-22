/* ============================================================
   Admin (break-glass) roles: superuser.
   Use for: restores, extensions, emergency only.
   Do NOT use for the running app or normal migrations.

   add password whe login is required: ALTER ROLE admin_prod
  WITH LOGIN
  PASSWORD 'VERY_LONG_RANDOM_PASSWORD';
   ============================================================ */
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'admin_dev') THEN
    CREATE ROLE admin_dev NOLOGIN SUPERUSER;
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'admin_test') THEN
    CREATE ROLE admin_test NOLOGIN SUPERUSER;
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'admin_prod') THEN
    CREATE ROLE admin_prod NOLOGIN SUPERUSER;
  END IF;
END$$;

-- Optional: allow admins to SET ROLE to migrator/app for debugging (handy)
GRANT migrator_dev  TO admin_dev;
GRANT migrator_test TO admin_test;
GRANT migrator_prod TO admin_prod;

GRANT app_dev  TO admin_dev;
GRANT app_test TO admin_test;
GRANT app_prod TO admin_prod;