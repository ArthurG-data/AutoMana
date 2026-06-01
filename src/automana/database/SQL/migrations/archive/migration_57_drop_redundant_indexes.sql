-- migration_57_drop_redundant_indexes.sql
--
-- Drops four indexes identified in the 2026-05-30 schema review
-- (docs/infrastructure/SCHEMA_NORMALIZATION_PLAN.md, Phase 1). Each target is
-- either an exact duplicate of an existing UNIQUE-constraint index or a strict
-- left-prefix of a broader composite index, so no read plan regresses while
-- write amplification and storage drop.
--
--   DROP idx_artists_name              -> covered by artists_ref_artist_name_key (UNIQUE)
--   DROP sets_set_code_idx             -> covered by sets_set_code_key (UNIQUE)
--   DROP idx_sealed_ext_id_type_value  -> covered by sealed_external_identifier_type_value_key (UNIQUE)
--   DROP idx_card_version_set_id       -> covered by card_version_set_coll_idx (set_id, collector_number)
--
-- Rollback (recreate the dropped indexes):
--   CREATE INDEX idx_artists_name ON card_catalog.artists_ref USING btree (artist_name);
--   CREATE INDEX sets_set_code_idx ON card_catalog.sets USING btree (set_code);
--   CREATE INDEX idx_sealed_ext_id_type_value ON card_catalog.sealed_external_identifier USING btree (sealed_identifier_ref_id, value);
--   CREATE INDEX idx_card_version_set_id ON card_catalog.card_version USING btree (set_id);

BEGIN;

DROP INDEX IF EXISTS card_catalog.idx_artists_name;
DROP INDEX IF EXISTS card_catalog.sets_set_code_idx;
DROP INDEX IF EXISTS card_catalog.idx_sealed_ext_id_type_value;
DROP INDEX IF EXISTS card_catalog.idx_card_version_set_id;

COMMIT;
