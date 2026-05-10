-- migration_27_ebay_sales.sql
-- Persist eBay seller order line items and link them into the pricing chain.
--
-- New artifacts:
--   app_integration.ebay_order_source_product — joining table: order ↔ source_product
--   pricing.data_provider 'ebay' seed row
--
-- Existing artifacts reused (no changes):
--   app_integration.ebay_order_status (migration_26) — order-level fulfillment status
--   pricing.price_source 'ebay' (06_prices.sql) — already seeded
--   pricing.source_product — one new row per (product_ref × ebay source) when a card resolves
--   pricing.price_observation — receives sold_avg_cents from resolved line items

BEGIN;

-- ── 1. Data provider ──────────────────────────────────────────────────────────

INSERT INTO pricing.data_provider (code, description)
VALUES ('ebay', 'eBay Fulfillment API — seller order history')
ON CONFLICT (code) DO NOTHING;

-- Note: price_source 'ebay' (source_id=5) is seeded in 06_prices.sql.

-- ── 2. Joining table: order line ↔ source_product ─────────────────────────────

CREATE TABLE IF NOT EXISTS app_integration.ebay_order_source_product (
    ebay_osp_id       BIGSERIAL    PRIMARY KEY,

    -- Order reference (requires ebay_order_status row to exist first)
    order_id          TEXT         NOT NULL,
    app_code          VARCHAR(50)  NOT NULL,
    FOREIGN KEY (order_id, app_code)
        REFERENCES app_integration.ebay_order_status(order_id, app_code)
        ON DELETE CASCADE,

    -- eBay listing identifiers (raw, always stored)
    item_id           TEXT         NOT NULL,   -- legacyItemId from Fulfillment API
    title             TEXT,                    -- raw listing title for display / re-resolution

    -- Resolved card identity — NULL until title resolves to a card
    source_product_id BIGINT
        REFERENCES pricing.source_product(source_product_id),

    -- Sale details
    quantity          SMALLINT     NOT NULL DEFAULT 1 CHECK (quantity > 0),
    sold_price_cents  INTEGER      NOT NULL CHECK (sold_price_cents >= 0),
    currency          VARCHAR(3)   NOT NULL DEFAULT 'USD',

    -- Card dimension defaults (updated on resolution)
    finish_id         SMALLINT     NOT NULL DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id      SMALLINT     DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id       SMALLINT     NOT NULL DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    -- Sale timestamp
    sold_at           TIMESTAMPTZ  NOT NULL,
    buyer_username    TEXT,

    -- Promotion flag: TRUE once row is upserted into pricing.price_observation
    promoted_to_obs   BOOLEAN      NOT NULL DEFAULT FALSE,

    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    UNIQUE (order_id, app_code, item_id)
);

CREATE INDEX IF NOT EXISTS idx_ebay_osp_source_product
    ON app_integration.ebay_order_source_product (source_product_id);

CREATE INDEX IF NOT EXISTS idx_ebay_osp_sold_at
    ON app_integration.ebay_order_source_product (sold_at DESC);

-- Partial index: unresolved lines waiting for card resolution
CREATE INDEX IF NOT EXISTS idx_ebay_osp_unresolved
    ON app_integration.ebay_order_source_product (app_code)
    WHERE source_product_id IS NULL;

-- Partial index: resolved lines not yet promoted to price_observation
CREATE INDEX IF NOT EXISTS idx_ebay_osp_unpromoted
    ON app_integration.ebay_order_source_product (app_code)
    WHERE promoted_to_obs = FALSE AND source_product_id IS NOT NULL;

-- ── 3. Grants ─────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_source_product TO app_backend;
GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_source_product TO app_celery;
GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_source_product TO app_rw, app_admin;
GRANT SELECT                  ON app_integration.ebay_order_source_product TO app_ro;
GRANT USAGE, SELECT ON SEQUENCE app_integration.ebay_order_source_product_ebay_osp_id_seq TO app_backend, app_celery, app_rw, app_admin;

COMMIT;
