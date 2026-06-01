-- migration_48_wire_gg_markets.sql
BEGIN;

-- Wire GG Sydney (market row exists, source row exists, source_id is NULL)
UPDATE markets.market_ref
SET source_id = (
    SELECT source_id FROM pricing.price_source WHERE code = 'gg_sydney'
)
WHERE name = 'Good Games Sydney'
  AND source_id IS NULL;

-- Add GG Brisbane (source row already exists from migration_46)
INSERT INTO markets.market_ref (name, city, country_code, api_url, source_id)
SELECT
    'Good Games Brisbane',
    'Brisbane',
    'AUD',
    'https://gg-brisbane.myshopify.com',
    source_id
FROM pricing.price_source
WHERE code = 'gg_brisbane'
ON CONFLICT (name) DO NOTHING;

COMMIT;
