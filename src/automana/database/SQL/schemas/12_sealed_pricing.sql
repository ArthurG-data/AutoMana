BEGIN;

-- Canonical schema state for sealed product pricing.
-- Reflects migration_51 + migration_53 + migration_54 + migration_55.
-- Applied on fresh container builds by the integration test runner.

-- ── card_catalog.sealed_type_ref ─────────────────────────────────────────────

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

-- ── card_catalog.sealed_subtype_ref ──────────────────────────────────────────

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
    ('other'),
    ('premium'),
    ('welcome')
ON CONFLICT (subtype_code) DO NOTHING;

-- ── card_catalog.sealed_product ──────────────────────────────────────────────

CREATE TABLE card_catalog.sealed_product (
    sealed_product_id  UUID        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id             UUID        REFERENCES card_catalog.sets(set_id),
    game_id            INTEGER     NOT NULL
                                   REFERENCES card_catalog.card_games_ref(game_id),
    sealed_type_id     SMALLINT    NOT NULL
                                   REFERENCES card_catalog.sealed_type_ref(sealed_type_id),
    sealed_subtype_id  SMALLINT
                                   REFERENCES card_catalog.sealed_subtype_ref(sealed_subtype_id),
    language_id        INTEGER     NOT NULL
                                   REFERENCES card_catalog.language_ref(language_id),
    name               TEXT        NOT NULL,
    release_date       DATE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sealed_product_set_id
    ON card_catalog.sealed_product (set_id);
CREATE INDEX idx_sealed_product_game_id
    ON card_catalog.sealed_product (game_id);
CREATE INDEX idx_sealed_product_language_id
    ON card_catalog.sealed_product (language_id);
CREATE INDEX idx_sealed_product_type_id
    ON card_catalog.sealed_product (sealed_type_id);
CREATE INDEX idx_sealed_product_subtype_id
    ON card_catalog.sealed_product (sealed_subtype_id)
    WHERE sealed_subtype_id IS NOT NULL;

-- ── card_catalog.sealed_identifier_ref ──────────────────────────────────────

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

-- ── card_catalog.sealed_external_identifier ──────────────────────────────────

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

-- ── pricing.sealed_price_latest ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pricing.sealed_price_latest (
    product_id          UUID        NOT NULL
                                    REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    source_id           SMALLINT    NOT NULL
                                    REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
                                    REFERENCES pricing.transaction_type(transaction_type_id),
    price_date          DATE        NOT NULL,
    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sealed_price_latest_pk PRIMARY KEY (product_id, source_id, transaction_type_id),
    CONSTRAINT chk_spl_nonneg CHECK (
        (list_low_cents  IS NULL OR list_low_cents  >= 0) AND
        (list_avg_cents  IS NULL OR list_avg_cents  >= 0) AND
        (sold_avg_cents  IS NULL OR sold_avg_cents  >= 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_spl_product_source
    ON pricing.sealed_price_latest (product_id, source_id);

-- ── pricing.mtg_sealed_products ─────────────────────────────────────────────

CREATE TABLE pricing.mtg_sealed_products (
    product_id        UUID NOT NULL PRIMARY KEY
        REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    sealed_product_id UUID NOT NULL
        REFERENCES card_catalog.sealed_product(sealed_product_id) ON DELETE CASCADE
);

CREATE INDEX idx_mtg_sealed_products_sealed_product_id
    ON pricing.mtg_sealed_products (sealed_product_id);

-- ── Grants ───────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON card_catalog.sealed_type_ref    TO app_rw, app_admin;
GRANT SELECT ON card_catalog.sealed_type_ref                    TO app_ro;
GRANT SELECT, INSERT, UPDATE ON card_catalog.sealed_subtype_ref TO app_rw, app_admin;
GRANT SELECT ON card_catalog.sealed_subtype_ref                 TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON card_catalog.sealed_product TO app_celery, app_rw, app_admin;
GRANT SELECT ON card_catalog.sealed_product              TO app_ro;
GRANT SELECT ON card_catalog.sealed_identifier_ref       TO app_celery, app_rw, app_admin, app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON card_catalog.sealed_external_identifier TO app_celery, app_rw, app_admin;
GRANT SELECT ON card_catalog.sealed_external_identifier  TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_price_latest TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_price_latest              TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.mtg_sealed_products TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.mtg_sealed_products              TO app_ro;

COMMIT;
