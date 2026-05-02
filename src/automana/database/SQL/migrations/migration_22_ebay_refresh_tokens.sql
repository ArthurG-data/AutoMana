-- migration_22_ebay_refresh_tokens.sql
--
-- Introduces app_integration.ebay_refresh_tokens: a durable, encrypted table
-- that stores one refresh token per (user_id, app_id) pair.
--
-- Access tokens are no longer written to disk. They live in Redis keyed by
-- "ebay:access_token:{user_id}:{app_code}" with a TTL of expires_in - 60s.
--
-- ebay_tokens is truncated here (dev only — all rows are expired test data and
-- cannot be backfilled without user_id). In a production context, run the
-- backfill DO block from plans/ebay-service_integration.md §7 before truncating.
--
-- ebay_tokens is retained structurally for one deploy cycle; it will be dropped
-- once ebay_refresh_tokens is confirmed stable in production.

BEGIN;

CREATE TABLE IF NOT EXISTS app_integration.ebay_refresh_tokens (
    user_id                 UUID        NOT NULL
        REFERENCES user_management.users(unique_id) ON DELETE CASCADE,
    app_id                  TEXT        NOT NULL
        REFERENCES app_integration.app_info(app_id) ON DELETE CASCADE,
    refresh_token_encrypted BYTEA       NOT NULL,
    issued_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at              TIMESTAMPTZ NOT NULL,
    rotated_at              TIMESTAMPTZ,
    key_version             SMALLINT    NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, app_id)
);

CREATE INDEX IF NOT EXISTS ix_ebay_refresh_expires
    ON app_integration.ebay_refresh_tokens (expires_at);

-- DEV: wipe stale test tokens; safe because all rows are expired and unlinked.
TRUNCATE app_integration.ebay_tokens RESTART IDENTITY;

COMMIT;
