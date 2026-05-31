-- migration_62_pricecharting_card_map.sql
--
-- Persistent PriceCharting product -> card_version match table.
--
-- The matching service (pricecharting.build_match_catalog) resolves each PC
-- product to a card_version_id via name + treatment + tcg-consensus scoring.
-- That work is recorded here so it runs ONCE per product: subsequent runs reuse
-- the stored match and only re-run the heuristic for products that are not yet
-- resolved. The table also records HOW the match was made (match_method) and how
-- confident it is (certainty 0-100, with the TCGPlayer vote count behind it), so
-- low-certainty matches can be reviewed. A `verified` row is a manual lock the
-- heuristic never overwrites.
--
-- card_version_id NULL = "matched as no DB card" (kept for visibility/reporting;
-- it does NOT suppress re-attempts — unmatched rows are always retried so that
-- later matching improvements apply).
--
-- The card_version <-> pricecharting_id link itself lives in
-- card_catalog.card_external_identifier (identifier_name 'pricecharting_id',
-- migration_61); this table is the match provenance + cache, not the identifier.

BEGIN;

CREATE TABLE IF NOT EXISTS pricing.pricecharting_card_map (
    pc_product_id    TEXT PRIMARY KEY,
    card_version_id  UUID REFERENCES card_catalog.card_version(card_version_id),
    set_code         TEXT,
    finish_id        SMALLINT,
    match_method     TEXT       NOT NULL DEFAULT 'none',
    certainty        SMALLINT   NOT NULL DEFAULT 0,
    tcg_vote_count   SMALLINT   NOT NULL DEFAULT 0,
    verified         BOOLEAN    NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pricecharting_card_map_cv
    ON pricing.pricecharting_card_map (card_version_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.pricecharting_card_map
    TO app_backend, app_celery;

COMMIT;
