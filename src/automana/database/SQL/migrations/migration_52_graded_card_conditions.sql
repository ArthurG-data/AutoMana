-- migration_52_graded_card_conditions.sql
--
-- Extends pricing.card_condition with four graded-slab tiers sourced from
-- PriceCharting (Grade 7, Grade 8, Grade 9, PSA 10 / Gem Mint).
--
-- Rationale: graded and ungraded cards are mutually exclusive — a card is
-- either raw (NM/LP/…) or slabbed. Re-using condition_id avoids adding a
-- new nullable column to the TimescaleDB hypertable price_observation and
-- its staging/aggregation layer, which would be an expensive migration.
--
-- condition_id mapping after this migration:
--   1  NM   Near Mint
--   2  LP   Lightly Played
--   3  MP   Moderately Played
--   4  HP   Heavily Played
--   5  DMG  Damaged
--   6  SP   Slightly Played
--   7  GR7  Graded 7
--   8  GR8  Graded 8
--   9  GR9  Graded 9
--  10  PSA10  PSA 10 / Gem Mint

INSERT INTO pricing.card_condition (condition_id, code, description)
VALUES
    (7,  'GR7',   'Graded 7'),
    (8,  'GR8',   'Graded 8'),
    (9,  'GR9',   'Graded 9'),
    (10, 'PSA10', 'PSA 10 / Gem Mint')
ON CONFLICT DO NOTHING;

-- Advance the sequence past the manually-inserted IDs so future auto-inserts
-- do not collide.
SELECT setval(
    pg_get_serial_sequence('pricing.card_condition', 'condition_id'),
    10,
    true
);
