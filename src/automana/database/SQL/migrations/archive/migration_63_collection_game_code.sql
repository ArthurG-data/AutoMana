-- migration_63_collection_game_code.sql
BEGIN;

-- Fix incorrect store URL set in migration_48
UPDATE markets.market_ref
SET api_url = 'https://tcg.goodgames.com.au'
WHERE name = 'Good Games Brisbane';

-- Add game classification to collection handles
-- NULL = unclassified, 'mtg' = active, 'pokemon'/'lorcana'/etc = stored but ignored
ALTER TABLE markets.collection_handles
    ADD COLUMN IF NOT EXISTS game_code VARCHAR;

COMMIT;
