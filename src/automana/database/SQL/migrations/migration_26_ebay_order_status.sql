-- migration_26_ebay_order_status.sql
BEGIN;

CREATE TABLE IF NOT EXISTS app_integration.ebay_order_status (
    order_id        TEXT         NOT NULL,
    app_code        VARCHAR(50)  NOT NULL
        REFERENCES app_integration.app_info(app_code) ON DELETE CASCADE,
    local_status    TEXT         NOT NULL
        CHECK (local_status IN ('sold', 'sent', 'in_transit', 'complete')),
    tracking_number TEXT,
    carrier_code    TEXT,
    shipped_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, app_code)
);

GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_status TO app_backend;
GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_status TO app_celery;

COMMIT;
