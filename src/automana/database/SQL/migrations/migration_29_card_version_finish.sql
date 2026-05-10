-- migration_29_card_version_finish.sql
-- Extend card_version to support treatment variants (finish) and language-exclusive
-- prints (lang), and track frame_effects (showcase, extendedart, borderless).
--
-- Why: switching from default_cards to all_cards exposes multiple treatments of
-- the same card in the same set (e.g. Ragavan non-foil, foil, showcase-foil in MH2)
-- as distinct Scryfall entries sharing the same collector_number.  The old UNIQUE
-- constraint (unique_card_id, set_id, collector_number) would silently drop every
-- variant after the first.  Adding finish + lang to the constraint lets each
-- distinct product coexist.
--
-- Also fixes a pre-existing silent bug: Japanese alternate-art planeswalkers
-- (WAR, STA) share collector_numbers with English versions; without lang in the
-- constraint the second language is always silently discarded.

BEGIN;

-- 1. Add finish (nonfoil / foil / etched / glossy / …)
ALTER TABLE card_catalog.card_version
    ADD COLUMN IF NOT EXISTS finish VARCHAR(20) NOT NULL DEFAULT 'nonfoil';

-- 2. Add frame_effects (showcase, extendedart, borderless, inverted, …)
ALTER TABLE card_catalog.card_version
    ADD COLUMN IF NOT EXISTS frame_effects TEXT[] NOT NULL DEFAULT '{}';

-- 3. Add lang (en, ja, ko, zhs, zht, …)
ALTER TABLE card_catalog.card_version
    ADD COLUMN IF NOT EXISTS lang VARCHAR(5) NOT NULL DEFAULT 'en';

-- 4. Replace old constraint that lacked finish + lang
ALTER TABLE card_catalog.card_version
    DROP CONSTRAINT IF EXISTS card_version_unique_card_id_set_id_collector_number_key;

-- New constraint: one row per (card, set, collector_number, finish, language).
-- Examples of rows that now coexist:
--   (Ragavan, MH2, 138, nonfoil, en)   ← regular non-foil
--   (Ragavan, MH2, 138, foil,    en)   ← foil
--   (Ragavan, MH2, 522, nonfoil, en)   ← showcase frame (different collector_number)
--   (Liliana, WAR,   3, foil,    en)   ← English foil
--   (Liliana, WAR,   3, foil,    ja)   ← Japanese alternate-art foil
DO $$
BEGIN
    ALTER TABLE card_catalog.card_version
        ADD CONSTRAINT card_version_unique_per_finish_lang
        UNIQUE (unique_card_id, set_id, collector_number, finish, lang);
EXCEPTION WHEN duplicate_object THEN
    NULL; -- Already created by schema on a fresh build
END;
$$;

COMMIT;
