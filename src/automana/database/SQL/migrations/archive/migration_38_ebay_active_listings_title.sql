BEGIN;

ALTER TABLE app_integration.ebay_active_listings
    ADD COLUMN IF NOT EXISTS title TEXT;

COMMIT;
