-- migration_64_deactivate_gg_sydney.sql
-- Good Games Sydney and Brisbane are both on tcg.goodgames.com.au — one store.
-- Nullify Sydney's api_url so the pipeline only fetches from gg_brisbane.
BEGIN;

UPDATE markets.market_ref
SET api_url = NULL
WHERE name = 'Good Games Sydney';

COMMIT;
