BEGIN;

-- Canonical schema state for sealed product pricing.
-- Reflects migration_51 + migration_53 + migration_54 + migration_55 + migration_56.
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

-- ── pricing.sealed_products ──────────────────────────────────────────────────

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

-- ── pricing.mtgjson_sealed_prices_staging ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS pricing.mtgjson_sealed_prices_staging (
    id              SERIAL      PRIMARY KEY,
    sealed_uuid     TEXT        NOT NULL,
    price_source    TEXT        NOT NULL,
    price_type      TEXT,
    currency        TEXT        NOT NULL,
    price_value     FLOAT       NOT NULL,
    price_date      DATE        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_msps_sealed_uuid
    ON pricing.mtgjson_sealed_prices_staging (sealed_uuid);
CREATE INDEX IF NOT EXISTS idx_msps_price_date
    ON pricing.mtgjson_sealed_prices_staging (price_date);

GRANT TRUNCATE ON pricing.mtgjson_sealed_prices_staging TO app_rw, app_admin;

-- ── Promotion procedure ───────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE pricing.load_price_observation_from_mtgjson_sealed_staging(
    batch_days INT DEFAULT 30
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_data_provider_id BIGINT;
    v_min DATE;
    v_max DATE;
    v_start DATE;
    v_end   DATE;
    v_upserted BIGINT := 0;
    v_deleted  BIGINT := 0;
    v_total_upserted BIGINT := 0;
    v_total_deleted  BIGINT := 0;
    v_is_ok BOOLEAN := FALSE;
BEGIN
    IF batch_days IS NULL OR batch_days <= 0 THEN
        RAISE EXCEPTION 'batch_days must be > 0 (got %)', batch_days;
    END IF;

    -- Normalize price_type
    UPDATE pricing.mtgjson_sealed_prices_staging
    SET price_type = CASE
        WHEN lower(price_type) IN ('retail', 'market') THEN 'sell'
        WHEN lower(price_type) IN ('buylist', 'directlow') THEN 'buy'
        ELSE lower(price_type)
    END;

    -- Normalize source names
    UPDATE pricing.mtgjson_sealed_prices_staging
    SET price_source = 'tcg'
    WHERE lower(price_source) = 'tcgplayer';

    COMMIT;

    SELECT dp.data_provider_id INTO v_data_provider_id
    FROM pricing.data_provider dp WHERE dp.code = 'mtgjson' LIMIT 1;

    IF v_data_provider_id IS NULL THEN
        RAISE EXCEPTION 'Missing pricing.data_provider row with code=mtgjson';
    END IF;

    SELECT min(price_date)::date, max(price_date)::date
    INTO v_min, v_max
    FROM pricing.mtgjson_sealed_prices_staging
    WHERE price_date IS NOT NULL;

    IF v_min IS NULL THEN
        RAISE NOTICE 'No rows in pricing.mtgjson_sealed_prices_staging to process.';
        RETURN;
    END IF;

    v_start := v_min;

    WHILE v_start <= v_max LOOP
        v_end := v_start + (batch_days - 1);

        BEGIN
            v_is_ok := FALSE;

            -- Upsert price_source rows for any new source codes in this batch
            INSERT INTO pricing.price_source (code, name, currency_code)
            SELECT DISTINCT s.price_source, s.price_source, s.currency
            FROM pricing.mtgjson_sealed_prices_staging s
            WHERE s.price_date BETWEEN v_start AND v_end
              AND s.price_source IS NOT NULL
              AND s.currency IS NOT NULL
            ON CONFLICT (code) DO NOTHING;

            WITH
            src AS (
                SELECT ps.source_id, ps.code, ps.currency_code
                FROM pricing.price_source ps
            ),
            prod AS (
                SELECT sp2.product_id, sp2.mtgjson_uuid
                FROM pricing.sealed_products sp2
            ),
            pairs AS (
                SELECT DISTINCT p.product_id, s.source_id
                FROM pricing.mtgjson_sealed_prices_staging st
                JOIN src s ON s.code = st.price_source
                JOIN prod p ON p.mtgjson_uuid = st.sealed_uuid
                WHERE st.price_date BETWEEN v_start AND v_end
                  AND st.sealed_uuid IS NOT NULL
            ),
            insert_source_product AS (
                INSERT INTO pricing.source_product (product_id, source_id)
                SELECT product_id, source_id FROM pairs
                ON CONFLICT (product_id, source_id) DO UPDATE
                    SET product_id = EXCLUDED.product_id
                RETURNING source_product_id, product_id, source_id
            ),
            staged AS (
                SELECT
                    s.id,
                    s.price_date AS ts_date,
                    s.price_source,
                    tt.transaction_type_id AS price_type_id,
                    s.currency,
                    s.sealed_uuid,
                    LEAST(round((s.price_value::NUMERIC) * 100), 2147483647::NUMERIC)::INT AS price_cents
                FROM pricing.mtgjson_sealed_prices_staging s
                JOIN pricing.transaction_type tt ON tt.transaction_type_code = s.price_type
                WHERE s.price_date BETWEEN v_start AND v_end
                  AND s.price_date IS NOT NULL
                  AND s.sealed_uuid IS NOT NULL
                  AND s.price_source IS NOT NULL
                  AND s.currency IS NOT NULL
                  AND s.price_value IS NOT NULL
            ),
            resolved AS (
                SELECT
                    st.id,
                    st.ts_date,
                    pricing.default_finish_id()    AS finish_id,
                    pricing.default_condition_id() AS condition_id,
                    card_catalog.default_language_id() AS language_id,
                    st.price_cents,
                    st.price_type_id,
                    isp.source_id,
                    isp.source_product_id,
                    prod.product_id
                FROM staged st
                JOIN src ON src.code = st.price_source
                JOIN prod ON prod.mtgjson_uuid = st.sealed_uuid
                JOIN insert_source_product isp
                    ON isp.product_id = prod.product_id
                   AND isp.source_id = src.source_id
            ),
            upserted AS (
                INSERT INTO pricing.price_observation (
                    ts_date, price_type_id, finish_id, condition_id, language_id,
                    list_low_cents, list_avg_cents, sold_avg_cents,
                    list_count, sold_count,
                    source_product_id, data_provider_id,
                    scraped_at, created_at, updated_at
                )
                SELECT DISTINCT ON (r.ts_date, r.source_product_id, r.price_type_id,
                                    r.finish_id, r.condition_id, r.language_id)
                    r.ts_date,
                    r.price_type_id,
                    r.finish_id,
                    r.condition_id,
                    r.language_id,
                    NULL::INT,
                    CASE WHEN r.price_type_id = 1 THEN r.price_cents END::INT,
                    CASE WHEN r.price_type_id = 2 THEN r.price_cents END::INT,
                    CASE WHEN r.price_type_id = 1 THEN 1 END::INT,
                    CASE WHEN r.price_type_id = 2 THEN 1 END::INT,
                    r.source_product_id,
                    v_data_provider_id,
                    now(), now(), now()
                FROM resolved r
                ORDER BY r.ts_date, r.source_product_id, r.price_type_id,
                         r.finish_id, r.condition_id, r.language_id
                ON CONFLICT (ts_date, source_product_id, price_type_id,
                             finish_id, condition_id, language_id, data_provider_id)
                DO UPDATE SET
                    list_avg_cents = EXCLUDED.list_avg_cents,
                    sold_avg_cents = EXCLUDED.sold_avg_cents,
                    list_count     = EXCLUDED.list_count,
                    sold_count     = EXCLUDED.sold_count,
                    scraped_at     = EXCLUDED.scraped_at,
                    updated_at     = now()
                RETURNING 1
            ),
            -- Upsert snapshot (advance only when newer) — same CTE chain so resolved is visible
            snapshot_insert AS (
                INSERT INTO pricing.sealed_price_latest (
                    product_id, source_id, transaction_type_id,
                    price_date, list_avg_cents, sold_avg_cents, n_providers, updated_at
                )
                SELECT DISTINCT ON (r.product_id, r.source_id, r.price_type_id)
                    r.product_id,
                    r.source_id,
                    r.price_type_id,
                    r.ts_date,
                    CASE WHEN r.price_type_id = 1 THEN r.price_cents END::INT,
                    CASE WHEN r.price_type_id = 2 THEN r.price_cents END::INT,
                    1::SMALLINT,
                    now()
                FROM resolved r
                ORDER BY r.product_id, r.source_id, r.price_type_id, r.ts_date DESC
                ON CONFLICT (product_id, source_id, transaction_type_id)
                DO UPDATE SET
                    price_date     = EXCLUDED.price_date,
                    list_avg_cents = EXCLUDED.list_avg_cents,
                    sold_avg_cents = EXCLUDED.sold_avg_cents,
                    n_providers    = EXCLUDED.n_providers,
                    updated_at     = now()
                WHERE EXCLUDED.price_date >= pricing.sealed_price_latest.price_date
            )
            SELECT count(*) INTO v_upserted FROM upserted;

            -- Delete resolved rows from staging
            WITH
            src AS (SELECT ps.source_id, ps.code FROM pricing.price_source ps),
            prod AS (SELECT sp2.product_id, sp2.mtgjson_uuid FROM pricing.sealed_products sp2),
            staged_ids AS (
                SELECT s.id
                FROM pricing.mtgjson_sealed_prices_staging s
                JOIN pricing.transaction_type tt ON tt.transaction_type_code = s.price_type
                JOIN src ON src.code = s.price_source
                JOIN prod ON prod.mtgjson_uuid = s.sealed_uuid
                JOIN pricing.source_product sp3
                    ON sp3.product_id = prod.product_id AND sp3.source_id = src.source_id
                WHERE s.price_date BETWEEN v_start AND v_end
                  AND s.price_date IS NOT NULL
                  AND s.sealed_uuid IS NOT NULL
                  AND s.price_source IS NOT NULL
                  AND s.currency IS NOT NULL
                  AND s.price_value IS NOT NULL
            )
            DELETE FROM pricing.mtgjson_sealed_prices_staging s
            USING staged_ids r WHERE s.id = r.id;

            GET DIAGNOSTICS v_deleted = ROW_COUNT;
            v_total_upserted := v_total_upserted + COALESCE(v_upserted, 0);
            v_total_deleted  := v_total_deleted  + COALESCE(v_deleted,  0);
            v_is_ok := TRUE;

        EXCEPTION WHEN OTHERS THEN
            v_is_ok := FALSE;
            RAISE WARNING 'Sealed batch % to % failed: %', v_start, v_end, SQLERRM;
        END;

        IF v_is_ok THEN
            RAISE NOTICE 'Sealed batch % to %: upserted %, deleted %',
                v_start, v_end, v_upserted, v_deleted;
            COMMIT;
        END IF;

        v_start := v_end + 1;
    END LOOP;

    RAISE NOTICE 'Done. Total upserted %, total deleted %', v_total_upserted, v_total_deleted;
END;
$$;

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
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_products              TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_products                                       TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.sealed_price_latest          TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.sealed_price_latest                                   TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.mtg_sealed_products          TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.mtg_sealed_products                                   TO app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.mtgjson_sealed_prices_staging TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.mtgjson_sealed_prices_staging                         TO app_ro;
GRANT EXECUTE ON PROCEDURE pricing.load_price_observation_from_mtgjson_sealed_staging(INT)
    TO app_celery, app_rw, app_admin;

COMMIT;
