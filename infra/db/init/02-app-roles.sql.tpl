
-- Roles
SELECT set_config('automana.admin_pw',   :'admin_pw',   false);
SELECT set_config('automana.backend_pw', :'backend_pw', false);
SELECT set_config('automana.celery_pw',  :'celery_pw',  false);
SELECT set_config('automana.agent_pw',   :'agent_pw',   false);
SELECT set_config('automana.readonly_pw',:'readonly_pw',false);

DO $$
DECLARE
  admin_pw   text := current_setting('automana.admin_pw');
  backend_pw text := current_setting('automana.backend_pw');
  celery_pw  text := current_setting('automana.celery_pw');
  agent_pw   text := current_setting('automana.agent_pw');
  readonly_pw text := current_setting('automana.readonly_pw');
  env text := current_database();
  s text;
  schemas text[] := ARRAY['card_catalogue','user_management','user_collection','app_integration','pricing','markets', 'ops'];
BEGIN
  -- Roles
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_admin') THEN CREATE ROLE app_admin NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_rw') THEN CREATE ROLE app_rw NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_ro') THEN CREATE ROLE app_ro NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agent_reader') THEN CREATE ROLE agent_reader NOLOGIN; END IF;

  -- Users (login roles)
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='automana_admin') THEN 
    EXECUTE format('CREATE USER automana_admin PASSWORD %L', admin_pw);
   END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_backend') THEN
      EXECUTE format('CREATE USER app_backend PASSWORD %L', backend_pw); 
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_celery')  THEN
     EXECUTE format('CREATE USER app_celery PASSWORD %L', celery_pw);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_readonly') THEN 
    EXECUTE format('CREATE USER app_readonly PASSWORD %L', readonly_pw);
   END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_agent') THEN 
    EXECUTE format('CREATE USER app_agent PASSWORD %L', agent_pw);
  END IF;
  ALTER ROLE automana_admin SET ROLE app_admin; 

  GRANT app_rw TO app_backend, app_celery;
  GRANT app_ro TO app_readonly;
  GRANT agent_reader TO app_agent;
  
  GRANT app_rw TO app_admin;
  GRANT app_ro TO app_admin;

  -- User -> admin role
  GRANT app_admin TO automana_admin;

  -- Revoke dangerous defaults
  REVOKE ALL ON SCHEMA public FROM PUBLIC;

  -- Base schema grants
  FOREACH s IN ARRAY schemas LOOP
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I;', s);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_rw, app_ro, agent_reader', s);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO app_rw', s);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO app_ro, agent_reader', s);
    EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO app_rw', s);
    EXECUTE format('GRANT CREATE ON SCHEMA %I TO app_admin', s);


    -- Default privileges must be per schema
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO app_ro', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw',
  s
);
EXECUTE format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
   GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw',
  s
);
EXECUTE format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE automana_admin IN SCHEMA %I
   GRANT SELECT ON TABLES TO app_ro',
  s
);
  END LOOP;

  -- ENV-specific overrides
  IF env LIKE '%prod%' THEN
    -- Example: in prod, agents only see card_catalogue + markets
    -- (replace with your real rule)
    REVOKE USAGE ON SCHEMA user_management, user_collection, app_integration, pricing FROM agent_reader;
  ELSIF env LIKE '%test%' THEN
    -- Example: allow broader read in test
    NULL;
  ELSE
    -- dev
    NULL;
  END IF;

END $$;