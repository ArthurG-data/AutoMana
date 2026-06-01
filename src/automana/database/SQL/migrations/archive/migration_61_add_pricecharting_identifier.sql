-- migration_61_add_pricecharting_identifier.sql
--
-- Register `pricecharting_id` as a card external-identifier type.
--
-- The PriceCharting matching service (pricecharting.build_match_catalog) maps a
-- PriceCharting product to a card_version_id via name + treatment scoring. Once
-- matched, the PriceCharting product_id is persisted into
-- card_catalog.card_external_identifier so future runs can resolve the card by
-- ID directly instead of re-running the heuristic match.
--
-- This adds the reference row only; the per-card values are written by the
-- service. Idempotent: ON CONFLICT on the unique identifier_name no-ops if the
-- row already exists (e.g. on a fresh rebuild where 02_card_schema.sql already
-- seeds it).
--
-- card_identifier_ref_id is SMALLSERIAL — the new row takes the next free id
-- (9, after mtgstock_id=8) without a hardcoded id.

INSERT INTO card_catalog.card_identifier_ref (identifier_name) VALUES
    ('pricecharting_id')
ON CONFLICT (identifier_name) DO NOTHING;
