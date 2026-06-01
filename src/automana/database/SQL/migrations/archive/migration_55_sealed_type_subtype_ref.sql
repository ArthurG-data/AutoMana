-- migration_55: Split sealed_product_type_ref into two separate ref tables.
--
-- Replaces the composite (category, subtype) ref table from migration_54 with:
--   card_catalog.sealed_type_ref    — product category  (booster_box, bundle, …)
--   card_catalog.sealed_subtype_ref — product subtype   (collector, play, …) — nullable on product
--
-- sealed_product gains sealed_type_id (NOT NULL) and sealed_subtype_id (NULL),
-- replacing the single sealed_product_type_id column.

BEGIN;

-- ── 1. Drop the combined ref (no FK data yet, safe) ──────────────────────────

ALTER TABLE card_catalog.sealed_product
    DROP COLUMN IF EXISTS sealed_product_type_id;

DROP TABLE IF EXISTS card_catalog.sealed_product_type_ref CASCADE;

-- ── 2. card_catalog.sealed_type_ref ──────────────────────────────────────────

CREATE TABLE card_catalog.sealed_type_ref (
    sealed_type_id SMALLINT    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type_code      TEXT        NOT NULL UNIQUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO card_catalog.sealed_type_ref (type_code) VALUES
    ('booster_pack'),
    ('booster_box'),
    ('booster_case'),
    ('bundle'),
    ('bundle_case'),
    ('box_set'),
    ('deck_box'),
    ('multiple_decks'),
    ('limited_aid_tool'),
    ('limited_aid_case'),
    ('subset')
ON CONFLICT (type_code) DO NOTHING;

-- ── 3. card_catalog.sealed_subtype_ref ───────────────────────────────────────

CREATE TABLE card_catalog.sealed_subtype_ref (
    sealed_subtype_id SMALLINT    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subtype_code      TEXT        NOT NULL UNIQUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO card_catalog.sealed_subtype_ref (subtype_code) VALUES
    ('collector'),
    ('play'),
    ('default'),
    ('gift_bundle'),
    ('prerelease_kit'),
    ('promotional'),
    ('starter_deck'),
    ('two_player_starter'),
    ('other')
ON CONFLICT (subtype_code) DO NOTHING;

-- ── 4. Add new columns to sealed_product ─────────────────────────────────────

ALTER TABLE card_catalog.sealed_product
    ADD COLUMN sealed_type_id    SMALLINT NOT NULL
        REFERENCES card_catalog.sealed_type_ref(sealed_type_id),
    ADD COLUMN sealed_subtype_id SMALLINT
        REFERENCES card_catalog.sealed_subtype_ref(sealed_subtype_id);

CREATE INDEX idx_sealed_product_type_id
    ON card_catalog.sealed_product (sealed_type_id);
CREATE INDEX idx_sealed_product_subtype_id
    ON card_catalog.sealed_product (sealed_subtype_id)
    WHERE sealed_subtype_id IS NOT NULL;

-- ── 5. Grants ─────────────────────────────────────────────────────────────────

GRANT SELECT ON card_catalog.sealed_type_ref    TO app_celery, app_rw, app_admin, app_ro;
GRANT SELECT ON card_catalog.sealed_subtype_ref TO app_celery, app_rw, app_admin, app_ro;

COMMIT;
