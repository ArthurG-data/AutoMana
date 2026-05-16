BEGIN;

-- 1. Create listing_template skeleton table
--    One row per (account × product × condition × finish × language × marketplace).
--    Template creation must call ENSURE_PRODUCT first so product_id is guaranteed to exist.
CREATE TABLE IF NOT EXISTS app_integration.listing_template (
    template_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    app_code       VARCHAR(50) NOT NULL
        REFERENCES app_integration.app_info(app_code),
    product_id     UUID        NOT NULL
        REFERENCES pricing.product_ref(product_id),
    condition_id   SMALLINT    NOT NULL
        REFERENCES pricing.card_condition(condition_id),
    finish_id      SMALLINT    NOT NULL
        REFERENCES card_catalog.card_finished(finish_id),
    language_id    SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),
    marketplace_id VARCHAR(10) NOT NULL DEFAULT '15',
    price_cents    INTEGER,
    quantity       INTEGER     NOT NULL DEFAULT 1,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (app_code, product_id, condition_id, finish_id, language_id, marketplace_id)
);

GRANT SELECT, INSERT, UPDATE ON app_integration.listing_template
    TO app_backend, app_celery;

-- 2. Extend ebay_active_listings with full variant + product link.
--    All new columns are nullable so existing rows are unaffected.
ALTER TABLE app_integration.ebay_active_listings
    ADD COLUMN IF NOT EXISTS product_id     UUID
        REFERENCES pricing.product_ref(product_id),
    ADD COLUMN IF NOT EXISTS condition_id   SMALLINT
        REFERENCES pricing.card_condition(condition_id),
    ADD COLUMN IF NOT EXISTS finish_id      SMALLINT
        REFERENCES card_catalog.card_finished(finish_id),
    ADD COLUMN IF NOT EXISTS language_id    SMALLINT
        REFERENCES card_catalog.language_ref(language_id),
    ADD COLUMN IF NOT EXISTS marketplace_id VARCHAR(10),
    ADD COLUMN IF NOT EXISTS template_id    UUID
        REFERENCES app_integration.listing_template(template_id);

CREATE INDEX IF NOT EXISTS idx_ebay_active_listings_marketplace
    ON app_integration.ebay_active_listings (marketplace_id)
    WHERE marketplace_id IS NOT NULL;

-- 3. Add marketplace_id to ebay_order_source_product so sold orders record which site.
ALTER TABLE app_integration.ebay_order_source_product
    ADD COLUMN IF NOT EXISTS marketplace_id VARCHAR(10);

COMMIT;
