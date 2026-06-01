-- migration_34_opentcg_source.sql
-- Adds tcgtracking data provider and manapool price source
-- for the Open TCG API at tcgtracking.com.

BEGIN;

-- New data provider for tcgtracking.com Open TCG API
INSERT INTO pricing.data_provider (code, description)
VALUES ('tcgtracking', 'Open TCG API — tcgtracking.com (TCGPlayer + Manapool aggregator)')
ON CONFLICT (code) DO NOTHING;

-- New price source for Manapool (EUR marketplace aggregated by tcgtracking.com)
INSERT INTO pricing.price_source (code, name, currency_code)
VALUES ('manapool', 'Manapool', 'EUR')
ON CONFLICT (code) DO NOTHING;

COMMIT;
