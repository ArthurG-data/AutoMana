-- migration_45_shopify_market_pipeline.sql
BEGIN;

-- 1. Link each market store to a price_source row
ALTER TABLE markets.market_ref
    ADD COLUMN IF NOT EXISTS source_id SMALLINT
        REFERENCES pricing.price_source(source_id);

-- 2. Store Shopify product handle (for buy-link URL) and title on product_ref
ALTER TABLE markets.product_ref
    ADD COLUMN IF NOT EXISTS handle TEXT,
    ADD COLUMN IF NOT EXISTS title  TEXT;

-- 3. Add source_id to staging so promote step knows which store each row is from
ALTER TABLE pricing.shopify_staging_raw
    ADD COLUMN IF NOT EXISTS source_id SMALLINT
        REFERENCES pricing.price_source(source_id);

-- 4. Register Shopify stores as price sources (AU stores to start)
INSERT INTO pricing.price_source (code, name, currency_code) VALUES
    ('gg_brisbane', 'Good Games Brisbane', 'AUD'),
    ('gg_sydney',   'Good Games Sydney',   'AUD')
ON CONFLICT (code) DO NOTHING;

-- 5. Register 'shopify' as a data provider
INSERT INTO pricing.data_provider (code, description)
VALUES ('shopify', 'Shopify Storefront /products.json scrape')
ON CONFLICT (code) DO NOTHING;

-- 6. Wire existing market_ref rows to their source rows
--    Update Good Games Brisbane market (adjust name to match your actual market_ref.name)
UPDATE markets.market_ref mr
SET source_id = ps.source_id
FROM pricing.price_source ps
WHERE ps.code = 'gg_brisbane'
  AND lower(mr.name) LIKE '%brisbane%'
  AND mr.source_id IS NULL;

UPDATE markets.market_ref mr
SET source_id = ps.source_id
FROM pricing.price_source ps
WHERE ps.code = 'gg_sydney'
  AND lower(mr.name) LIKE '%sydney%'
  AND mr.source_id IS NULL;

COMMIT;
