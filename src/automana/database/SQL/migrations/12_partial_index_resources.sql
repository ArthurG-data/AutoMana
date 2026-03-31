-- ============================================================
-- Migration 12: Add partial unique index on ops.resources
--               for rows where canonical_key IS NULL.
--
-- The existing index ux_resources_source_type_natkey covers
-- (source_id, external_type, external_id, canonical_key).
-- PostgreSQL's ON CONFLICT inference requires an exact column
-- match, and NULL values are not considered equal in unique
-- indexes, so that index cannot be used for upserts where
-- canonical_key is NULL.
--
-- This partial index enables:
--   ON CONFLICT (source_id, external_type, external_id)
--     WHERE canonical_key IS NULL
-- which is the correct conflict target for Scryfall bulk data.
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS ux_resources_no_canonical_key
ON ops.resources (source_id, external_type, external_id)
WHERE canonical_key IS NULL;
