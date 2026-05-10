-- migration_28_cvi_image_uris.sql
-- Move image_uris storage from per-illustration to per-card-version.
--
-- Root cause: card_catalog.illustrations uses illustration_id as PK, and
-- Scryfall reuses the same illustration_id across reprints of the same artwork
-- in different sets. The prior ON CONFLICT DO UPDATE in insert_full_card_version
-- overwrote image_uris with the last-processed printing's URLs, so cards from
-- earlier sets displayed another set's card image (right art, wrong set symbol).
--
-- Fix: add image_uris to card_version_illustration (one row per card_version)
-- so each printing keeps its own Scryfall image URL.
-- The illustrations table retains illustration_id as an art-deduplication anchor.

BEGIN;

ALTER TABLE card_catalog.card_version_illustration
    ADD COLUMN IF NOT EXISTS image_uris JSONB;

-- Best-effort back-fill: copy current image_uris from the shared illustrations
-- row into every card_version_illustration that references it.
-- This gives a reasonable starting point; a full pipeline re-run will populate
-- correct per-version URLs once insert_full_card_version is updated.
UPDATE card_catalog.card_version_illustration cvi
SET image_uris = ill.image_uris
FROM card_catalog.illustrations ill
WHERE cvi.illustration_id = ill.illustration_id;

COMMIT;
