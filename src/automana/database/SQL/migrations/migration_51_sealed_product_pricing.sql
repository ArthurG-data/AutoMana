-- migration_51: Sealed product pricing tables and grants.
--
-- Creates two new tables:
--   pricing.sealed_products        — subtype of product_ref for sealed MTG products
--   pricing.sealed_price_latest    — current-price snapshot keyed on product_id
--
-- Card pricing pipeline (mtg_card_products, price_observation, etc.) is untouched.

-- ── sealed_products ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing.sealed_products (
    product_id      UUID        NOT NULL PRIMARY KEY
                                REFERENCES pricing.product_ref(product_id) ON DELETE CASCADE,
    set_id          UUID        REFERENCES card_catalog.sets(set_id),
    name            TEXT        NOT NULL,
    product_type    TEXT        NOT NULL,
    mtgjson_uuid    TEXT        NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sealed_products_set_id
    ON pricing.sealed_products (set_id);
CREATE INDEX IF NOT EXISTS idx_sealed_products_mtgjson_uuid
    ON pricing.sealed_products (mtgjson_uuid);

-- ── sealed_price_latest ───────────────────────────────────────────────────────
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

-- ── Grants ────────────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_products    TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_products                            TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_price_latest TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_price_latest                        TO app_ro;
