BEGIN;

-- ============================================================================
-- Migration 25: Fix 2 & Fix 3 — Art Card + Token Resolution for MTGStock Price Pipeline
-- ============================================================================
--
-- Problem: 7.2M rows stuck in stg_price_observation_reject due to:
--   - Fix 2 (680K rows): Art cards use AAINR-style MTGStocks codes but ainr in Scryfall
--   - Fix 3 (3.8M rows): Tokens have NULL collector_number; base set codes don't map to 't'-prefixed token sets
--
-- Solution: Two new mapping tables + two resolution paths in load_staging_prices_batched + resolve_price_rejects
--
-- Expected recovery: ~4.5M rows (~62% of stuck rows)

-- ============================================================================
-- CREATE MAPPING TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS pricing.mtgstock_art_set_map (
    mtgstocks_set_code  TEXT PRIMARY KEY,
    scryfall_set_code   TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE pricing.mtgstock_art_set_map IS
    'Maps MTGStocks "A"-prefixed art set codes (AAINR, ADFT, etc.) to lowercase Scryfall equivalents (ainr, adft, etc.)';

CREATE TABLE IF NOT EXISTS pricing.mtgstock_token_set_map (
    mtgstocks_set_code  TEXT PRIMARY KEY,
    token_set_code      TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE pricing.mtgstock_token_set_map IS
    'Maps MTGStocks base set codes (CMM, WHO, MH3) to Scryfall "t"-prefixed token set codes (tcmm, twho, tmh3)';

-- ============================================================================
-- SEED MAPPING TABLES
-- ============================================================================

-- Fix 2: Art set mappings (manually from MTGSTOCK_REJECT_ANALYSIS.md known values)
INSERT INTO pricing.mtgstock_art_set_map (mtgstocks_set_code, scryfall_set_code) VALUES
    ('AAINR', 'ainr'),   -- Astral Arena art cards
    ('ADFT',  'adft'),   -- Duskmourn art cards
    ('AEOE',  'aeoe'),   -- Eldritch Ordeals
    ('AFIN',  'afin'),   -- Final Format
    ('AATDM', 'aatdm'),  -- Against the Darkness
    ('ASLD',  'asld'),   -- Summer Legends
    ('APRE',  'apre'),   -- Prerelease cards (if applicable)
    ('AMAT',  'amat')    -- Mat cards (if applicable)
ON CONFLICT (mtgstocks_set_code) DO NOTHING;

-- Fix 3: Token set mappings (dynamically generated from catalog)
-- First, check if card_catalog.set_type_list_ref exists and has token sets
INSERT INTO pricing.mtgstock_token_set_map (mtgstocks_set_code, token_set_code)
SELECT
    UPPER(SUBSTR(s.set_code, 2)) AS mtgstocks_set_code,
    s.set_code AS token_set_code
FROM card_catalog.sets s
JOIN card_catalog.set_type_list_ref stl ON s.set_type_id = stl.set_type_id
WHERE stl.set_type = 'token'
  AND LENGTH(s.set_code) >= 2
  AND SUBSTR(s.set_code, 1, 1) = 't'
  AND UPPER(SUBSTR(s.set_code, 2)) NOT IN (SELECT mtgstocks_set_code FROM pricing.mtgstock_token_set_map)
ON CONFLICT (mtgstocks_set_code) DO NOTHING;

-- ============================================================================
-- GRANTS
-- ============================================================================

GRANT SELECT ON pricing.mtgstock_art_set_map   TO app_celery, app_rw, app_ro, app_backend, app_admin;
GRANT SELECT ON pricing.mtgstock_token_set_map TO app_celery, app_rw, app_ro, app_backend, app_admin;

-- ============================================================================
-- UPDATE PROCEDURES
-- ============================================================================

-- This migration updates:
-- 1. pricing.load_staging_prices_batched — adds tmp_map_art, tmp_map_token; extends tmp_resolved
-- 2. pricing.resolve_price_rejects — adds map_art, map_token CTEs; extends final SELECT
--
-- These procedures are updated in the schema file (06_prices.sql) via CREATE OR REPLACE.
-- Running the schema file after this migration will install the updated versions.
-- For backwards compatibility, the full procedure bodies are NOT repeated here.
-- Instead, the procedures are updated during schema application.

-- Note: If running migrations in isolation (not rebuilding schema), copy the updated
-- procedure CREATE OR REPLACE blocks from 06_prices.sql into this migration after
-- the GRANT statements above. For now, we rely on schema-rebuild workflow.

COMMIT;
