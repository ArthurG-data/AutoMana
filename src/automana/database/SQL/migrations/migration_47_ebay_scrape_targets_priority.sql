BEGIN;

ALTER TABLE pricing.ebay_scrape_targets
    ADD COLUMN IF NOT EXISTS priority_score INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN pricing.ebay_scrape_targets.priority_score
    IS 'MAX(sold_avg_cents) from price_observation in the last 7 days. Used to weight nightly scrape order by value × staleness.';

COMMIT;
