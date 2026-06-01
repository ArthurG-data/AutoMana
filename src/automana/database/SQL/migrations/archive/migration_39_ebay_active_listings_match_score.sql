BEGIN;
ALTER TABLE app_integration.ebay_active_listings
    ADD COLUMN IF NOT EXISTS match_score REAL;
COMMIT;
