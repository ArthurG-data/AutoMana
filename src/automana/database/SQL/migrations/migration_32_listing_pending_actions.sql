-- migration_32_listing_pending_actions.sql
-- Creates the staged listing action queue.

CREATE TABLE IF NOT EXISTS app_integration.listing_pending_actions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id         TEXT        NOT NULL,
    user_id         UUID        NOT NULL,
    app_code        TEXT        NOT NULL,
    action_type     TEXT        NOT NULL CHECK (action_type IN ('raise','lower','hold','draft')),
    strategy_kind   TEXT        NOT NULL,
    suggested_price NUMERIC(10,2),
    status          TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','done','failed')),
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_listing_actions_pending
    ON app_integration.listing_pending_actions (created_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_listing_actions_item
    ON app_integration.listing_pending_actions (item_id);

GRANT SELECT, INSERT, UPDATE ON app_integration.listing_pending_actions TO app_celery;
GRANT SELECT, INSERT, UPDATE ON app_integration.listing_pending_actions TO app_backend;
