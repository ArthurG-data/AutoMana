-- migration_33_scryfall_prices.sql
-- Adds cardhoarder price source (TIX/MTGO prices from Scryfall bulk data)
-- and purchase_uris column to card_version for marketplace buy links.

BEGIN;

-- Ensure TIX currency exists before inserting price_source (FK requirement)
INSERT INTO pricing.currency_ref (currency_code, currency_name)
VALUES ('TIX', 'Magic Online Tickets')
ON CONFLICT (currency_code) DO NOTHING;

-- Add cardhoarder source (for tix/MTGO prices from Scryfall bulk data)
INSERT INTO pricing.price_source (code, name, currency_code)
VALUES ('cardhoarder', 'Cardhoarder', 'TIX')
ON CONFLICT (code) DO NOTHING;

-- Add purchase_uris to card_version (marketplace buy links for frontend)
ALTER TABLE card_catalog.card_version
ADD COLUMN IF NOT EXISTS purchase_uris JSONB;

COMMIT;
