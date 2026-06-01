-- 08_ebay_orders.sql
-- eBay order persistence tables.
-- Placed after 06_prices.sql because tables reference pricing.default_finish_id()
-- and pricing.default_condition_id() which are defined in 06_prices.sql.

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

CREATE TABLE IF NOT EXISTS app_integration.ebay_order_source_product (
    ebay_osp_id       BIGSERIAL    PRIMARY KEY,
    order_id          TEXT         NOT NULL,
    app_code          VARCHAR(50)  NOT NULL,
    FOREIGN KEY (order_id, app_code)
        REFERENCES app_integration.ebay_order_status(order_id, app_code)
        ON DELETE CASCADE,
    item_id           TEXT         NOT NULL,
    title             TEXT,
    source_product_id BIGINT
        REFERENCES pricing.source_product(source_product_id),
    quantity          SMALLINT     NOT NULL DEFAULT 1 CHECK (quantity > 0),
    sold_price_cents  INTEGER      NOT NULL CHECK (sold_price_cents >= 0),
    currency          VARCHAR(3)   NOT NULL DEFAULT 'USD',
    finish_id         SMALLINT     NOT NULL DEFAULT pricing.default_finish_id()
        REFERENCES card_catalog.card_finished(finish_id),
    condition_id      SMALLINT     DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id       SMALLINT     NOT NULL DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),
    sold_at           TIMESTAMPTZ  NOT NULL,
    buyer_username    TEXT,
    promoted_to_obs   BOOLEAN      NOT NULL DEFAULT FALSE,
    marketplace_id    VARCHAR(10),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (order_id, app_code, item_id)
);

CREATE INDEX IF NOT EXISTS idx_ebay_osp_source_product
    ON app_integration.ebay_order_source_product (source_product_id);
CREATE INDEX IF NOT EXISTS idx_ebay_osp_sold_at
    ON app_integration.ebay_order_source_product (sold_at DESC);
CREATE INDEX IF NOT EXISTS idx_ebay_osp_unresolved
    ON app_integration.ebay_order_source_product (app_code)
    WHERE source_product_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_ebay_osp_unpromoted
    ON app_integration.ebay_order_source_product (app_code)
    WHERE promoted_to_obs = FALSE AND source_product_id IS NOT NULL;
