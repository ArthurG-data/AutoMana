-- migration_29_japanese_card_filter.sql
-- Filter v_card_versions_complete to exclude Japanese cards that have an
-- English equivalent at the same set + collector_number.
-- Keeps: EN cards, Japan-exclusive sets, Japanese alt-art (e.g. STA 64-126),
--        stamped promos with ★ collector numbers (e.g. WAR JP walkers).
-- Drops 3 dependent views via CASCADE; recreates them identically after.

DROP MATERIALIZED VIEW IF EXISTS card_catalog.v_card_versions_complete CASCADE;

CREATE MATERIALIZED VIEW card_catalog.v_card_versions_complete AS
WITH
card_types_agg AS (
    SELECT
        ct.unique_card_id,
        array_agg(ct.type_name ORDER BY ct.type_name) FILTER (WHERE ct.type_category = 'type') AS types,
        array_agg(ct.type_name ORDER BY ct.type_name) FILTER (WHERE ct.type_category = 'subtype') AS subtypes,
        array_agg(ct.type_name ORDER BY ct.type_name) FILTER (WHERE ct.type_category = 'supertype') AS supertypes
    FROM card_catalog.card_types ct
    GROUP BY ct.unique_card_id
),
colors_agg AS (
    SELECT
        cci.unique_card_id,
        array_agg(cr.color_name ORDER BY cr.color_name) AS color_identity
    FROM card_catalog.card_color_identity cci
    JOIN card_catalog.colors_ref cr ON cci.color_id = cr.color_id
    GROUP BY cci.unique_card_id
),
keywords_agg AS (
    SELECT
        ck.unique_card_id,
        array_agg(kr.keyword_name ORDER BY kr.keyword_name) AS keywords
    FROM card_catalog.card_keyword ck
    JOIN card_catalog.keywords_ref kr ON ck.keyword_id = kr.keyword_id
    GROUP BY ck.unique_card_id
),
legalities_agg AS (
    SELECT
        l.unique_card_id,
        jsonb_object_agg(
            fr.format_name,
            lsr.legal_status
        ) AS legalities
    FROM card_catalog.legalities l
    JOIN card_catalog.formats_ref fr ON l.format_id = fr.format_id
    JOIN card_catalog.legal_status_ref lsr ON l.legality_id = lsr.legality_id
    GROUP BY l.unique_card_id
),
games_agg AS (
    SELECT
        gcv.card_version_id,
        array_agg(gr.game_description ORDER BY gr.game_description) AS games
    FROM card_catalog.games_card_version gcv
    JOIN card_catalog.games_ref gr ON gcv.game_id = gr.game_id
    GROUP BY gcv.card_version_id
),
promo_types_agg AS (
    SELECT
        pc.card_version_id,
        array_agg(ptr.promo_type_desc ORDER BY ptr.promo_type_desc) AS promo_types
    FROM card_catalog.promo_card pc
    JOIN card_catalog.promo_types_ref ptr ON pc.promo_id = ptr.promo_id
    GROUP BY pc.card_version_id
),
card_stats_agg AS (
    SELECT
        cvs.card_version_id,
        MAX(CASE WHEN csr.stat_name = 'power' THEN cvs.stat_value END) AS power,
        MAX(CASE WHEN csr.stat_name = 'toughness' THEN cvs.stat_value END) AS toughness,
        MAX(CASE WHEN csr.stat_name = 'loyalty' THEN cvs.stat_value END) AS loyalty,
        MAX(CASE WHEN csr.stat_name = 'defense' THEN cvs.stat_value END) AS defense
    FROM card_catalog.card_version_stats cvs
    JOIN card_catalog.card_stats_ref csr ON cvs.stat_id = csr.stat_id
    GROUP BY cvs.card_version_id
),
illustrations_agg AS (
    SELECT
        cvi.card_version_id,
        jsonb_agg(
            jsonb_build_object(
                'illustration_id', cvi.illustration_id,
                'image_uris', cvi.image_uris,
                'added_on', i.added_on,
                'artist_id', ar.artist_id,
                'artist_name', ar.artist_name
            )
            ORDER BY i.added_on NULLS LAST, cvi.illustration_id
        ) AS illustrations
    FROM card_catalog.card_version_illustration cvi
    JOIN card_catalog.illustrations i ON cvi.illustration_id = i.illustration_id
    LEFT JOIN card_catalog.illustration_artist ia ON i.illustration_id = ia.illustration_id
    LEFT JOIN card_catalog.artists_ref ar ON ia.artist_id = ar.artist_id
    GROUP BY cvi.card_version_id
),
card_faces_agg AS (
    SELECT
        cf.card_version_id,
        jsonb_agg(
            jsonb_build_object(
                'face_index', cf.face_index,
                'name', cf.name,
                'mana_cost', cf.mana_cost,
                'type_line', cf.type_line,
                'oracle_text', cf.oracle_text,
                'power', cf.power,
                'toughness', cf.toughness,
                'flavor_text', cf.flavor_text
            ) ORDER BY cf.face_index
        ) AS card_faces
    FROM card_catalog.card_faces cf
    GROUP BY cf.card_version_id
)
SELECT
    cv.card_version_id,
    cv.unique_card_id,
    ucr.card_name,

    s.set_id,
    s.set_name,
    s.set_code,
    cv.collector_number,

    ucr.cmc,
    ucr.mana_cost,
    cv.oracle_text,
    ucr.reserved,

    COALESCE(cta.types, ARRAY[]::text[]) AS types,
    COALESCE(cta.subtypes, ARRAY[]::text[]) AS subtypes,
    COALESCE(cta.supertypes, ARRAY[]::text[]) AS supertypes,

    CASE
        WHEN array_length(COALESCE(cta.supertypes, ARRAY[]::text[]), 1) > 0
        THEN array_to_string(cta.supertypes, ' ') || ' '
        ELSE ''
    END ||
    CASE
        WHEN array_length(COALESCE(cta.types, ARRAY[]::text[]), 1) > 0
        THEN array_to_string(cta.types, ' ')
        ELSE ''
    END ||
    CASE
        WHEN array_length(COALESCE(cta.subtypes, ARRAY[]::text[]), 1) > 0
        THEN ' — ' || array_to_string(cta.subtypes, ' ')
        ELSE ''
    END AS type_line,

    COALESCE(ca.color_identity, ARRAY[]::text[]) AS color_identity,
    COALESCE(ka.keywords, ARRAY[]::text[]) AS keywords,

    csa.power,
    csa.toughness,
    csa.loyalty,
    csa.defense,

    rr.rarity_name,
    bcr.border_color_name,
    fr.frame_year,
    lr.layout_name,

    cv.frame_effects,
    cv.lang,

    cv.is_promo,
    cv.is_digital,
    cv.is_oversized,
    cv.full_art,
    cv.textless,
    cv.booster,
    cv.variation,
    cv.is_multifaced,

    COALESCE(ia.illustrations, '[]'::jsonb) AS illustrations,

    COALESCE(la.legalities, '{}'::jsonb) AS legalities,
    COALESCE(ga.games, ARRAY[]::text[]) AS games,
    COALESCE(pta.promo_types, ARRAY[]::text[]) AS promo_types,
    COALESCE(cfa.card_faces, '[]'::jsonb) AS card_faces,

    CASE
        WHEN cv.is_multifaced THEN jsonb_array_length(COALESCE(cfa.card_faces, '[]'::jsonb))
        ELSE 1
    END AS face_count,

    to_tsvector('english',
        ucr.card_name || ' ' ||
        COALESCE(cv.oracle_text, '') || ' ' ||
        COALESCE(array_to_string(cta.types, ' '), '') || ' ' ||
        COALESCE(array_to_string(cta.subtypes, ' '), '') || ' ' ||
        COALESCE(array_to_string(ka.keywords, ' '), '')
    ) AS search_vector,

    CURRENT_TIMESTAMP AS materialized_at

FROM card_catalog.card_version cv
JOIN card_catalog.unique_cards_ref ucr ON cv.unique_card_id = ucr.unique_card_id
JOIN card_catalog.sets s ON cv.set_id = s.set_id
JOIN card_catalog.rarities_ref rr ON cv.rarity_id = rr.rarity_id
JOIN card_catalog.border_color_ref bcr ON cv.border_color_id = bcr.border_color_id
JOIN card_catalog.frames_ref fr ON cv.frame_id = fr.frame_id
JOIN card_catalog.layouts_ref lr ON cv.layout_id = lr.layout_id
LEFT JOIN card_types_agg cta ON ucr.unique_card_id = cta.unique_card_id
LEFT JOIN colors_agg ca ON ucr.unique_card_id = ca.unique_card_id
LEFT JOIN keywords_agg ka ON ucr.unique_card_id = ka.unique_card_id
LEFT JOIN legalities_agg la ON ucr.unique_card_id = la.unique_card_id
LEFT JOIN games_agg ga ON cv.card_version_id = ga.card_version_id
LEFT JOIN promo_types_agg pta ON cv.card_version_id = pta.card_version_id
LEFT JOIN card_stats_agg csa ON cv.card_version_id = csa.card_version_id
LEFT JOIN illustrations_agg ia ON cv.card_version_id = ia.card_version_id
LEFT JOIN card_faces_agg cfa ON cv.card_version_id = cfa.card_version_id
WHERE cv.lang = 'en'
   OR NOT EXISTS (
       SELECT 1 FROM card_catalog.card_version en_cv
       WHERE en_cv.set_id = cv.set_id
         AND en_cv.collector_number = cv.collector_number
         AND en_cv.lang = 'en'
   );

CREATE UNIQUE INDEX idx_v_card_versions_complete_pk ON card_catalog.v_card_versions_complete (card_version_id);
CREATE INDEX idx_v_card_versions_complete_name ON card_catalog.v_card_versions_complete (card_name);
CREATE INDEX idx_v_card_versions_complete_set ON card_catalog.v_card_versions_complete (set_name, collector_number);
CREATE INDEX idx_v_card_versions_complete_cmc ON card_catalog.v_card_versions_complete (cmc);
CREATE INDEX idx_v_card_versions_complete_colors ON card_catalog.v_card_versions_complete USING GIN (color_identity);
CREATE INDEX idx_v_card_versions_complete_types ON card_catalog.v_card_versions_complete USING GIN (types);
CREATE INDEX idx_v_card_versions_complete_promo_types ON card_catalog.v_card_versions_complete USING GIN (promo_types);
CREATE INDEX idx_v_card_versions_complete_rarity ON card_catalog.v_card_versions_complete (rarity_name);
CREATE INDEX idx_v_card_versions_complete_search ON card_catalog.v_card_versions_complete USING GIN (search_vector);
CREATE INDEX idx_v_card_versions_complete_legalities ON card_catalog.v_card_versions_complete USING GIN (legalities);

-- Recreate views dropped by CASCADE
CREATE OR REPLACE VIEW card_catalog.v_cards_by_name AS
SELECT
    card_name,
    COUNT(*) AS version_count,
    array_agg(DISTINCT set_name ORDER BY set_name) AS available_sets,
    MIN(cmc) AS min_cmc,
    MAX(cmc) AS max_cmc,
    array_agg(DISTINCT rarity_name ORDER BY rarity_name) AS rarities
FROM card_catalog.v_card_versions_complete
GROUP BY card_name;

CREATE OR REPLACE VIEW card_catalog.v_cards_latest_version AS
SELECT DISTINCT ON (card_name)
    card_version_id,
    card_name,
    set_name,
    collector_number,
    cmc,
    mana_cost,
    oracle_text,
    type_line,
    rarity_name,
    power,
    toughness,
    loyalty
FROM card_catalog.v_card_versions_complete
ORDER BY card_name, materialized_at DESC;

CREATE OR REPLACE VIEW card_catalog.v_set_statistics AS
SELECT
    set_name,
    set_code,
    COUNT(*) AS total_cards,
    COUNT(*) FILTER (WHERE rarity_name = 'common') AS common_count,
    COUNT(*) FILTER (WHERE rarity_name = 'uncommon') AS uncommon_count,
    COUNT(*) FILTER (WHERE rarity_name = 'rare') AS rare_count,
    COUNT(*) FILTER (WHERE rarity_name = 'mythic') AS mythic_count,
    array_agg(DISTINCT color_identity) FILTER (WHERE array_length(color_identity, 1) > 0) AS color_combinations,
    AVG(cmc) AS avg_cmc,
    MIN(cmc) AS min_cmc,
    MAX(cmc) AS max_cmc
FROM card_catalog.v_card_versions_complete
GROUP BY set_name, set_code;
