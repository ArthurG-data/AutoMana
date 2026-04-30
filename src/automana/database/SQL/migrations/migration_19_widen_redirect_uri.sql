-- migration_19_widen_redirect_uri.sql
-- Widens app_info.redirect_uri from VARCHAR(50) to VARCHAR(255)
-- so full ngrok/production URLs fit without truncation.
BEGIN;

ALTER TABLE app_integration.app_info
    ALTER COLUMN redirect_uri TYPE VARCHAR(255);

COMMIT;
