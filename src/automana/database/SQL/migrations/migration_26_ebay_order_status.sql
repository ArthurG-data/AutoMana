-- migration_26_ebay_order_status.sql
BEGIN;

CREATE TABLE IF NOT EXISTS app_integration.ebay_order_status (
    order_id        TEXT         NOT NULL,
    app_id          TEXT         NOT NULL
        REFERENCES app_integration.app_info(app_id) ON DELETE CASCADE,
    local_status    TEXT         NOT NULL
        CHECK (local_status IN ('sold', 'sent', 'in_transit', 'complete')),
    tracking_number TEXT,
    carrier_code    TEXT,
    shipped_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, app_id)
);

GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_status TO app_backend;
GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_status TO app_celery;
GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_status TO app_rw, app_admin;
GRANT SELECT                  ON app_integration.ebay_order_status TO app_ro;

COMMIT;
