-- migration_54: Restructure sealed product schema to mirror the card catalog pattern.
--
-- Replaces the interim pricing.sealed_products / pricing.sealed_identifier_ref /
-- pricing.sealed_external_identifier tables (migration_51 + 53) with a fully
-- normalised layout:
--
--   card_catalog.sealed_product_type_ref    — taxonomy ref (category + subtype)
--   card_catalog.sealed_product             — central entity (set, game, type, language)
--   card_catalog.sealed_identifier_ref      — identifier type ref
--   card_catalog.sealed_external_identifier — external ID values per product
--   pricing.mtg_sealed_products             — pricing subtype (product_ref → sealed_product)
--
-- pricing.sealed_price_latest is untouched (already references product_ref).

BEGIN;

-- ── 1. Remove migration_51/53 tables ────────────────────────────────────────
-- No real data was ever ingested; the one test-seed row is synthetic.

DROP TABLE IF EXISTS pricing.sealed_external_identifier CASCADE;
DROP TABLE IF EXISTS pricing.sealed_identifier_ref      CASCADE;
DROP TABLE IF EXISTS pricing.sealed_products            CASCADE;

-- ── 2. card_catalog.sealed_product_type_ref ──────────────────────────────────

CREATE TABLE card_catalog.sealed_product_type_ref (
    sealed_product_type_id SMALLINT    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category               TEXT        NOT NULL,
    subtype                TEXT        NOT NULL DEFAULT '',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sealed_product_type_category_subtype_key UNIQUE (category, subtype)
);

-- Taxonomy sourced from MTGJson sealedProduct.category + sealedProduct.subtype.
-- Add rows as new product types appear; existing rows are never removed.
INSERT INTO card_catalog.sealed_product_type_ref (category, subtype) VALUES
    ('booster_pack',     'collector'),
    ('booster_pack',     'play'),
    ('booster_pack',     'prerelease_kit'),
    ('booster_pack',     'promotional'),
    ('booster_pack',     'other'),
    ('booster_pack',     ''),
    ('booster_box',      'collector'),
    ('booster_box',      'play'),
    ('booster_box',      ''),
    ('booster_case',     'collector'),
    ('booster_case',     'play'),
    ('booster_case',     ''),
    ('bundle',           'default'),
    ('bundle',           'gift_bundle'),
    ('bundle',           ''),
    ('bundle_case',      'default'),
    ('bundle_case',      ''),
    ('box_set',          'starter_deck'),
    ('box_set',          'two_player_starter'),
    ('box_set',          'other'),
    ('box_set',          ''),
    ('deck_box',         ''),
    ('multiple_decks',   ''),
    ('limited_aid_tool', ''),
    ('limited_aid_case', ''),
    ('subset',           '')
ON CONFLICT (category, subtype) DO NOTHING;

-- ── 3. card_catalog.sealed_product ───────────────────────────────────────────

CREATE TABLE card_catalog.sealed_product (
    sealed_product_id      UUID        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id                 UUID        REFERENCES card_catalog.sets(set_id),
    game_id                INTEGER     NOT NULL
                                       REFERENCES card_catalog.card_games_ref(game_id),
    sealed_product_type_id SMALLINT
                                       REFERENCES card_catalog.sealed_product_type_ref(sealed_product_type_id),
    language_id            INTEGER     NOT NULL
                                       REFERENCES card_catalog.language_ref(language_id),
    name                   TEXT        NOT NULL,
    release_date           DATE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sealed_product_set_id
    ON card_catalog.sealed_product (set_id);
CREATE INDEX idx_sealed_product_game_id
    ON card_catalog.sealed_product (game_id);
CREATE INDEX idx_sealed_product_language_id
    ON card_catalog.sealed_product (language_id);

-- ── 4. card_catalog.sealed_identifier_ref ────────────────────────────────────

CREATE TABLE card_catalog.sealed_identifier_ref (
    sealed_identifier_ref_id SMALLINT    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identifier_name          TEXT        NOT NULL UNIQUE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO card_catalog.sealed_identifier_ref (identifier_name) VALUES
    ('mtgjson_uuid'),
    ('tcgplayer_product_id'),
    ('cardkingdom_id'),
    ('mcm_id'),
    ('scg_id'),
    ('abu_id')
ON CONFLICT (identifier_name) DO NOTHING;

-- ── 5. card_catalog.sealed_external_identifier ───────────────────────────────

CREATE TABLE card_catalog.sealed_external_identifier (
    sealed_identifier_ref_id SMALLINT    NOT NULL
        REFERENCES card_catalog.sealed_identifier_ref(sealed_identifier_ref_id),
    sealed_product_id        UUID        NOT NULL
        REFERENCES card_catalog.sealed_product(sealed_product_id) ON DELETE CASCADE,
    value                    TEXT        NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sealed_external_identifier_pkey
        PRIMARY KEY (sealed_product_id, sealed_identifier_ref_id),
    CONSTRAINT sealed_external_identifier_type_value_key
        UNIQUE (sealed_identifier_ref_id, value)
);

CREATE INDEX idx_sealed_ext_id_type_value
    ON card_catalog.sealed_external_identifier (sealed_identifier_ref_id, value);

-- ── 6. pricing.mtg_sealed_products ───────────────────────────────────────────

CREATE TABLE pricing.mtg_sealed_products (
    product_id        UUID NOT NULL PRIMARY KEY
        REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    sealed_product_id UUID NOT NULL
        REFERENCES card_catalog.sealed_product(sealed_product_id) ON DELETE CASCADE
);

CREATE INDEX idx_mtg_sealed_products_sealed_product_id
    ON pricing.mtg_sealed_products (sealed_product_id);

-- ── 7. Grants ─────────────────────────────────────────────────────────────────

GRANT SELECT ON card_catalog.sealed_product_type_ref    TO app_celery, app_rw, app_admin, app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON card_catalog.sealed_product TO app_celery, app_rw, app_admin;
GRANT SELECT ON card_catalog.sealed_product              TO app_ro;
GRANT SELECT ON card_catalog.sealed_identifier_ref       TO app_celery, app_rw, app_admin, app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON card_catalog.sealed_external_identifier TO app_celery, app_rw, app_admin;
GRANT SELECT ON card_catalog.sealed_external_identifier  TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.mtg_sealed_products TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.mtg_sealed_products              TO app_ro;

COMMIT;
