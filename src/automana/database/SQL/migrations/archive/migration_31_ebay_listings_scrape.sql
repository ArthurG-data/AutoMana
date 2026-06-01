BEGIN;

CREATE TABLE IF NOT EXISTS app_integration.ebay_active_listings (
    item_id         TEXT         PRIMARY KEY,
    app_code        VARCHAR(50)  NOT NULL
        REFERENCES app_integration.app_info(app_code) ON DELETE CASCADE,
    card_version_id UUID         NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    listed_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ebay_active_listings_app
    ON app_integration.ebay_active_listings (app_code);

CREATE INDEX IF NOT EXISTS idx_ebay_active_listings_card
    ON app_integration.ebay_active_listings (card_version_id);

GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_active_listings
    TO app_backend, app_celery;

CREATE TABLE IF NOT EXISTS pricing.ebay_scraped_sold (
    scrape_id         BIGSERIAL    PRIMARY KEY,
    item_id           TEXT         NOT NULL UNIQUE,
    title             TEXT         NOT NULL,
    source_product_id BIGINT       REFERENCES pricing.source_product(source_product_id),
    price_cents       INTEGER      NOT NULL CHECK (price_cents >= 0),
    currency          VARCHAR(3)   NOT NULL DEFAULT 'USD',
    condition_id      SMALLINT     REFERENCES pricing.card_condition(condition_id),
    finish_id         SMALLINT     NOT NULL DEFAULT pricing.default_finish_id(),
    language_id       SMALLINT     NOT NULL DEFAULT card_catalog.default_language_id(),
    sold_at           TIMESTAMPTZ  NOT NULL,
    scraped_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    promoted_to_obs   BOOLEAN      NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_ebay_scraped_unpromoted
    ON pricing.ebay_scraped_sold (source_product_id)
    WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ebay_scraped_sold_at
    ON pricing.ebay_scraped_sold (sold_at DESC);

GRANT SELECT, INSERT, UPDATE ON pricing.ebay_scraped_sold
    TO app_backend, app_celery;

GRANT USAGE ON SEQUENCE pricing.ebay_scraped_sold_scrape_id_seq
    TO app_backend, app_celery;

COMMIT;
