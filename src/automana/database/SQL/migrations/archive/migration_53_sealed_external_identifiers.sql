-- migration_53: Normalise sealed product external identifiers.
--
-- Cards use card_catalog.card_identifier_ref + card_external_identifier.
-- This migration brings sealed products to the same pattern:
--   pricing.sealed_identifier_ref  — ref table of identifier types
--   pricing.sealed_external_identifier — (product_id, type, value) rows
--
-- mtgjson_uuid is migrated out of sealed_products into the new table and
-- the column is dropped. tcgplayer_product_id is seeded as a second type
-- so the tcgtracking ingestion can resolve sealed catalog rows by TCGPlayer ID.

-- ── sealed_identifier_ref ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing.sealed_identifier_ref (
    sealed_identifier_ref_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identifier_name          TEXT        NOT NULL UNIQUE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO pricing.sealed_identifier_ref (identifier_name) VALUES
    ('mtgjson_uuid'),
    ('tcgplayer_product_id')
ON CONFLICT (identifier_name) DO NOTHING;

-- ── sealed_external_identifier ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing.sealed_external_identifier (
    sealed_identifier_ref_id SMALLINT NOT NULL
        REFERENCES pricing.sealed_identifier_ref(sealed_identifier_ref_id),
    product_id               UUID     NOT NULL
        REFERENCES pricing.sealed_products(product_id) ON DELETE CASCADE,
    value                    TEXT     NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sealed_external_identifier_pkey
        PRIMARY KEY (product_id, sealed_identifier_ref_id),
    -- Each external ID value is globally unique within an identifier type.
    CONSTRAINT sealed_external_identifier_type_value_key
        UNIQUE (sealed_identifier_ref_id, value)
);

CREATE INDEX IF NOT EXISTS idx_sealed_ext_id_type_value
    ON pricing.sealed_external_identifier (sealed_identifier_ref_id, value);

-- ── Migrate existing mtgjson_uuid rows ────────────────────────────────────────
INSERT INTO pricing.sealed_external_identifier (sealed_identifier_ref_id, product_id, value)
SELECT sir.sealed_identifier_ref_id, sp.product_id, sp.mtgjson_uuid
FROM   pricing.sealed_products sp
CROSS  JOIN pricing.sealed_identifier_ref sir
WHERE  sir.identifier_name = 'mtgjson_uuid'
  AND  sp.mtgjson_uuid IS NOT NULL
ON CONFLICT DO NOTHING;

-- ── Drop the now-redundant column ─────────────────────────────────────────────
ALTER TABLE pricing.sealed_products DROP COLUMN IF EXISTS mtgjson_uuid;

-- ── Grants ─────────────────────────────────────────────────────────────────────
GRANT SELECT ON pricing.sealed_identifier_ref TO app_celery, app_rw, app_admin, app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_external_identifier TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_external_identifier TO app_ro;
