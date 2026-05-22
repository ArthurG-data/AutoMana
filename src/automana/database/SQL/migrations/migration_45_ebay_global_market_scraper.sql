BEGIN;

-- 1. Watchlist: cards to scrape across all markets nightly.
CREATE TABLE IF NOT EXISTS pricing.ebay_scrape_targets (
    card_version_id  UUID         PRIMARY KEY
        REFERENCES card_catalog.card_version(card_version_id),
    added_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_scraped_at  TIMESTAMPTZ,
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    added_by         TEXT         NOT NULL DEFAULT 'auto'
);

GRANT SELECT, INSERT, UPDATE ON pricing.ebay_scrape_targets
    TO app_backend, app_celery;

-- 2. Daily FX rates for AUD→USD and CAD→USD normalisation.
CREATE TABLE IF NOT EXISTS pricing.fx_rates (
    rate_date      DATE          NOT NULL,
    from_currency  VARCHAR(3)    NOT NULL,
    to_currency    VARCHAR(3)    NOT NULL DEFAULT 'USD',
    rate           NUMERIC(12,6) NOT NULL,
    fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, from_currency, to_currency)
);

GRANT SELECT, INSERT, UPDATE ON pricing.fx_rates
    TO app_backend, app_celery;

-- 3. Tag each scraped sold row with its source eBay marketplace.
ALTER TABLE pricing.ebay_scraped_sold
    ADD COLUMN IF NOT EXISTS marketplace_id VARCHAR(20) NOT NULL DEFAULT 'EBAY-US';

COMMIT;
