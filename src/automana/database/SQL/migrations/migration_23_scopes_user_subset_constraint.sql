-- migration_23_scopes_user_subset_constraint.sql
--
-- Fixes the scopes_user table:
--   1. app_id made NOT NULL (was nullable — broke per-app scoping)
--   2. PK changed from (scope_id, user_id) to (user_id, app_id, scope_id)
--      so a user can hold scopes for multiple apps independently
--   3. Trigger enforces that every inserted/updated row has a corresponding
--      (scope_id, app_id) row in scope_app — user scopes MUST be a subset
--      of the scopes granted to the app

BEGIN;

-- 1. Delete any orphaned rows (app_id NULL or not a valid subset) before
--    applying the NOT NULL constraint and trigger.
DELETE FROM app_integration.scopes_user
WHERE app_id IS NULL
   OR NOT EXISTS (
       SELECT 1 FROM app_integration.scope_app sa
        WHERE sa.scope_id = scopes_user.scope_id
          AND sa.app_id   = scopes_user.app_id
   );

-- 2. Fix app_id nullability and PK.
ALTER TABLE app_integration.scopes_user
    ALTER COLUMN app_id SET NOT NULL;

ALTER TABLE app_integration.scopes_user
    DROP CONSTRAINT scopes_user_pkey;

ALTER TABLE app_integration.scopes_user
    ADD CONSTRAINT scopes_user_pkey PRIMARY KEY (user_id, app_id, scope_id);

-- 3. Trigger: reject any user scope that is not in scope_app for the same app.
CREATE OR REPLACE FUNCTION app_integration.check_user_scope_is_app_subset()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM app_integration.scope_app sa
         WHERE sa.scope_id = NEW.scope_id
           AND sa.app_id   = NEW.app_id
    ) THEN
        RAISE EXCEPTION
            'scope_id=% is not granted to app_id=% — user scopes must be a subset of the app''s scope_app entries',
            NEW.scope_id, NEW.app_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_scopes_user_subset_check ON app_integration.scopes_user;
CREATE TRIGGER trg_scopes_user_subset_check
    BEFORE INSERT OR UPDATE ON app_integration.scopes_user
    FOR EACH ROW EXECUTE FUNCTION app_integration.check_user_scope_is_app_subset();

COMMIT;
