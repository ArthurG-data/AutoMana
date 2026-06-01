-- migration_58_unique_cards_fk_and_tz_fixes.sql
--
-- Small correctness/normalization fixes from the 2026-05-30 schema review
-- (docs/infrastructure/SCHEMA_NORMALIZATION_PLAN.md, Phase 3). Two independent,
-- low-risk changes:
--
-- 3.1  card_catalog.unique_cards_ref.other_face_id is a nullable self-reference
--      (DFC / split-card pairing) with NO foreign key and NO index. Add both:
--      enforces referential integrity and avoids seq scans when the self-link is
--      traversed. Verified 0 orphan other_face_id values before adding the FK.
--
-- 3.2  pricing.shopify_staging_raw.scraped_at was TIMESTAMP WITHOUT TIME ZONE
--      while every other timestamp column in the schema is TIMESTAMPTZ. Normalize
--      it to TIMESTAMPTZ (interpreting existing values as UTC). Table is a
--      transient staging buffer (currently empty) so this is effectively free.
--
-- Rollback:
--   ALTER TABLE card_catalog.unique_cards_ref DROP CONSTRAINT fk_unique_cards_other_face;
--   DROP INDEX card_catalog.idx_unique_cards_ref_other_face;
--   ALTER TABLE pricing.shopify_staging_raw
--     ALTER COLUMN scraped_at TYPE TIMESTAMP USING scraped_at AT TIME ZONE 'UTC';

BEGIN;

-- 3.1 self-referential FK + partial index on the DFC pairing column
ALTER TABLE card_catalog.unique_cards_ref
    ADD CONSTRAINT fk_unique_cards_other_face
    FOREIGN KEY (other_face_id)
    REFERENCES card_catalog.unique_cards_ref(unique_card_id);

CREATE INDEX IF NOT EXISTS idx_unique_cards_ref_other_face
    ON card_catalog.unique_cards_ref(other_face_id)
    WHERE other_face_id IS NOT NULL;

-- 3.2 normalize Shopify staging timestamp to timezone-aware
ALTER TABLE pricing.shopify_staging_raw
    ALTER COLUMN scraped_at TYPE TIMESTAMPTZ USING scraped_at AT TIME ZONE 'UTC';

COMMIT;
