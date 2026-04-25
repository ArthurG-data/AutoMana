

-- TABLES------------------------------------
BEGIN;
CREATE TABLE IF NOT EXISTS card_catalog.unique_cards_ref (
    unique_card_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    card_name TEXT NOT NULL UNIQUE,
    cmc INT,
    mana_cost VARCHAR(50),
    reserved BOOL DEFAULT(false),
    other_face_id UUID DEFAULT(NULL),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_catalog.border_color_ref (
    border_color_id SERIAL PRIMARY KEY, 
    border_color_name VARCHAR(20) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

--not as intended, the subtyoes should be ckleand to remove punctuation and have a type name reference table, mismatch in unique_card_id
CREATE TABLE IF NOT EXISTS card_catalog.card_types (
    unique_card_id UUID NOT NULL REFERENCES card_catalog.unique_cards_ref(unique_card_id),
    type_name VARCHAR(20) NOT NULL,
    type_category TEXT CHECK (type_category IN ('type', 'subtype', 'supertype')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (unique_card_id, type_name)
);

CREATE TABLE IF NOT EXISTS card_catalog.rarities_ref (
    rarity_id SERIAL PRIMARY KEY,
    rarity_name VARCHAR(20) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_catalog.artists_ref (
    artist_id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- VARCHAR(255): real Scryfall artist credits routinely exceed 50 chars
    -- (collabs like "John Avon / Seb McKinnon", studio credits, etc.)
    artist_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (artist_name)
);
CREATE INDEX IF NOT EXISTS idx_artists_name ON card_catalog.artists_ref(artist_name);

-- Sentinel row used by card_catalog.insert_full_card_version when the
-- Scryfall payload carries neither `artist_ids` nor `artist` (basic
-- lands, tokens, reprints with scrubbed metadata). Having a concrete
-- FK target keeps illustration_artist referentially complete instead
-- of rejecting ~38k rows per Scryfall import with 23503 errors.
INSERT INTO card_catalog.artists_ref (artist_id, artist_name)
VALUES ('00000000-0000-0000-0000-000000000001', 'Unknown Artist')
ON CONFLICT (artist_name) DO NOTHING;
CREATE TABLE IF NOT EXISTS card_catalog.frames_ref (
    frame_id SERIAL PRIMARY KEY,
    frame_year VARCHAR(20) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_catalog.layouts_ref (
    layout_id SERIAL PRIMARY KEY,
    layout_name VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_catalog.keywords_ref (
    keyword_id SERIAL PRIMARY KEY,
    keyword_name VARCHAR(50) UNIQUE NOT NULL,
    first_added TIMESTAMPTZ DEFAULT now(),
    last_used DATE  DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

--mismatch some unique card id not present, not migrated yet
CREATE TABLE IF NOT EXISTS card_catalog.card_keyword (
    unique_card_id UUID REFERENCES card_catalog.unique_cards_ref(unique_card_id),
    keyword_id INT NOT NULL REFERENCES card_catalog.keywords_ref(keyword_id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (unique_card_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS card_catalog.colors_ref (
    color_id SERIAL PRIMARY KEY,
    color_name VARCHAR(20) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_catalog.color_produced (
    unique_card_id UUID REFERENCES card_catalog.unique_cards_ref(unique_card_id),
    color_id int NOT NULL REFERENCES card_catalog.colors_ref(color_id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (unique_card_id, color_id)
);

-- same issue with wrong unique_card_id ref type — left as-is for now
CREATE TABLE IF NOT EXISTS card_catalog.card_color_identity (
    unique_card_id UUID REFERENCES card_catalog.unique_cards_ref(unique_card_id),
    color_id int NOT NULL REFERENCES card_catalog.colors_ref(color_id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (unique_card_id, color_id)
);

-- same issue with wrong unique_card_id ref type — left as-is for now
CREATE TABLE IF NOT EXISTS card_catalog.formats_ref (
    format_id SERIAL PRIMARY KEY,
    format_name VARCHAR(20) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_catalog.legal_status_ref (
    legality_id SERIAL PRIMARY KEY, 
    legal_status VARCHAR(20) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
-- same issue with wrong unique_card_id ref type — left as-is for now
CREATE TABLE IF NOT EXISTS card_catalog.legalities (
    unique_card_id UUID REFERENCES card_catalog.unique_cards_ref(unique_card_id),
    format_id INT NOT NULL REFERENCES card_catalog.formats_ref(format_id),
    legality_id INT NOT NULL REFERENCES card_catalog.legal_status_ref(legality_id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY(unique_card_id, format_id)
);

CREATE TABLE IF NOT EXISTS card_catalog.card_version (
    card_version_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    unique_card_id UUID NOT NULL REFERENCES card_catalog.unique_cards_ref(unique_card_id),
    oracle_text TEXT,
    set_id UUID NOT NULL REFERENCES card_catalog.sets(set_id),
    collector_number VARCHAR(50),
    rarity_id INT NOT NULL REFERENCES card_catalog.rarities_ref(rarity_id),
    border_color_id INT NOT NULL REFERENCES card_catalog.border_color_ref(border_color_id),
    frame_id int NOT NULL REFERENCES card_catalog.frames_ref(frame_id),
    layout_id INT NOT NULL REFERENCES card_catalog.layouts_ref(layout_id), 
    is_promo BOOL DEFAULT false, 
    is_digital BOOL DEFAULT false,
    is_oversized BOOL DEFAULT false,
    full_art BOOLEAN DEFAULT false,
    textless BOOLEAN DEFAULT false,
    booster BOOLEAN DEFAULT true,
    variation BOOLEAN DEFAULT false,   
    is_multifaced BOOLEAN DEFAULT false, 
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (unique_card_id, set_id, collector_number)
);

CREATE TABLE IF NOT EXISTS card_catalog.illustrations(
    illustration_id UUID PRIMARY KEY, 
    image_uris jsonb,
    added_on TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_catalog.illustration_artist (
    illustration_id uuid NOT NULL REFERENCES card_catalog.illustrations(illustration_id),
    artist_id uuid NOT NULL REFERENCES card_catalog.artists_ref(artist_id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (illustration_id, artist_id)
);

CREATE TABLE IF NOT EXISTS card_catalog.card_version_illustration (
    card_version_id UUID PRIMARY KEY REFERENCES card_catalog.card_version(card_version_id),
    illustration_id UUID NOT NULL REFERENCES card_catalog.illustrations(illustration_id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

--need to be added
CREATE TABLE IF NOT EXISTS card_catalog.games_ref (
    game_id SERIAL PRIMARY KEY,
    game_description  VARCHAR(20) NOT NULL UNIQUE ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
--new stats table
CREATE TABLE IF NOT EXISTS card_catalog.card_stats_ref (
    stat_id SERIAL PRIMARY KEY,
    stat_name VARCHAR(20) NOT NULL UNIQUE,
    stat_description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
--reference  newly added
INSERT INTO card_catalog.card_stats_ref (stat_name, stat_description) VALUES
('power', 'Creature power value'),
('toughness', 'Creature toughness value'),
('loyalty', 'Planeswalker loyalty value'),
('defense', 'Battle defense value')
ON CONFLICT (stat_name) DO NOTHING;

-- versioned stats table
CREATE TABLE IF NOT EXISTS card_catalog.card_version_stats (
    card_version_id UUID NOT NULL REFERENCES card_catalog.card_version(card_version_id),
    stat_id INT NOT NULL REFERENCES card_catalog.card_stats_ref(stat_id),
    stat_value TEXT NOT NULL,
    PRIMARY KEY (card_version_id, stat_id)
);

CREATE TABLE IF NOT EXISTS card_catalog.games_card_version (
    game_id INT NOT NULL REFERENCES card_catalog.games_ref(game_id),
    card_version_id UUID NOT NULL REFERENCES card_catalog.card_version(card_version_id),
    PRIMARY KEY (game_id, card_version_id)
);
CREATE TABLE IF NOT EXISTS card_catalog.promo_types_ref (
    promo_id SERIAL PRIMARY KEY,
    promo_type_desc TEXT UNIQUE NOT NULL 
);

CREATE TABLE IF NOT EXISTS card_catalog.promo_card (
    promo_id INT NOT NULL REFERENCES card_catalog.promo_types_ref(promo_id),
    card_version_id UUID NOT NULL REFERENCES card_catalog.card_version(card_version_id),
	PRIMARY KEY (promo_id, card_version_id)
);

CREATE TABLE IF NOT EXISTS card_catalog.card_faces (
    card_faces_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    card_version_id UUID NOT NULL REFERENCES card_catalog.card_version(card_version_id),
    face_index INT,
    name TEXT NOT NULL,
    mana_cost TEXT,
    -- NULLABLE: Scryfall legitimately omits type_line on continuation
    -- faces of multi-face cards (Adventure cards, MDFC cont'd, etc.).
    -- The Pydantic `CardFace` model already types this as Optional[str].
    type_line TEXT,
    oracle_text TEXT,
    power TEXT,
    toughness TEXT,
    flavor_text TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (card_version_id, face_index)
);

CREATE TABLE card_catalog.face_illustration (
  face_id uuid NOT NULL REFERENCES card_catalog.card_faces(card_faces_id),
  illustration_id uuid NOT NULL REFERENCES card_catalog.illustrations(illustration_id),
  created_at timestamptz DEFAULT now(),
  PRIMARY KEY (face_id, illustration_id)
);
-- card_identifier_ref must be declared BEFORE card_external_identifier
-- because the latter has a FK pointing at the former. Previously reversed
-- → CREATE TABLE failed at replay time with "relation does not exist".
CREATE TABLE IF NOT EXISTS card_catalog.card_identifier_ref (
    card_identifier_ref_id SMALLSERIAL PRIMARY KEY,
    identifier_name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (identifier_name)
);

INSERT INTO card_catalog.card_identifier_ref (identifier_name) VALUES
    ('scryfall_id'),
    ('oracle_id'),
    ('multiverse_id'),
    ('tcgplayer_id'),
    ('tcgplayer_etched_id'),
    ('cardmarket_id')
ON CONFLICT (identifier_name) DO NOTHING;

-- The (card_identifier_ref_id, value) pair is intentionally NOT unique. Some
-- upstream catalogs (TCGPlayer, Cardmarket) issue one product ID per physical
-- product, but Scryfall correctly models foil/nonfoil printings of that product
-- as separate card_version rows. ~1.2k card_version pairs share a tcgplayer_id
-- in the dev DB (mostly old-style starred collector numbers like #213★ + #213
-- in 8ED–10E). Forcing uniqueness here would silently drop one printing per
-- pair and break price-lookup attribution. See:
--   docs/superpowers/specs/2026-04-25-shared-tcgplayer-cardmarket-id-fix-design.md
-- The non-unique index keeps reverse lookups (`WHERE value = $tcgplayer_id`)
-- index-seekable.
CREATE TABLE IF NOT EXISTS card_catalog.card_external_identifier (
    card_identifier_ref_id SMALLINT NOT NULL REFERENCES card_catalog.card_identifier_ref(card_identifier_ref_id),
    card_version_id UUID NOT NULL REFERENCES card_catalog.card_version(card_version_id),
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (card_version_id, card_identifier_ref_id)
);

CREATE INDEX IF NOT EXISTS idx_card_external_identifier_ref_value
    ON card_catalog.card_external_identifier (card_identifier_ref_id, value);


CREATE TABLE IF NOT EXISTS card_catalog.card_games_ref (
    game_id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO card_catalog.card_games_ref (code, name) VALUES
('mtg', 'Magic: The Gathering')
ON CONFLICT (code) DO NOTHING;



CREATE TABLE IF NOT EXISTS card_catalog.scryfall_migration(
    id uuid PRIMARY KEY NOT NULL,
    uri TEXT NOT NULL,
    performed_at DATE NOT NULL DEFAULT CURRENT_DATE,
    migration_strategy TEXT NOT NULL,
    old_scryfall_id UUID NOT NULL,
    new_scryfall_id UUID,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
--VIEWS -------------------------------------
CREATE OR REPLACE VIEW card_catalog.v_card_version_count AS
SELECT
    uc.unique_card_id,
    uc.card_name,
    COUNT(cv.card_version_id) AS version_count
FROM card_catalog.unique_cards_ref uc
LEFT JOIN card_catalog.card_version cv ON uc.unique_card_id = cv.unique_card_id
GROUP BY uc.unique_card_id, uc.card_name;

CREATE MATERIALIZED VIEW card_catalog.v_card_versions_complete AS
WITH 
-- Card types aggregated
card_types_agg AS (
    SELECT 
        ct.unique_card_id,
        array_agg(ct.type_name ORDER BY ct.type_name) FILTER (WHERE ct.type_category = 'type') AS types,
        array_agg(ct.type_name ORDER BY ct.type_name) FILTER (WHERE ct.type_category = 'subtype') AS subtypes,
        array_agg(ct.type_name ORDER BY ct.type_name) FILTER (WHERE ct.type_category = 'supertype') AS supertypes
    FROM card_catalog.card_types ct
    GROUP BY ct.unique_card_id
),
-- Colors aggregated
colors_agg AS (
    SELECT 
        cci.unique_card_id,
        array_agg(cr.color_name ORDER BY cr.color_name) AS color_identity
    FROM card_catalog.card_color_identity cci
    JOIN card_catalog.colors_ref cr ON cci.color_id = cr.color_id
    GROUP BY cci.unique_card_id
),
-- Keywords aggregated
keywords_agg AS (
    SELECT 
        ck.unique_card_id,
        array_agg(kr.keyword_name ORDER BY kr.keyword_name) AS keywords
    FROM card_catalog.card_keyword ck
    JOIN card_catalog.keywords_ref kr ON ck.keyword_id = kr.keyword_id
    GROUP BY ck.unique_card_id
),
-- Legalities aggregated
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
-- Games aggregated
games_agg AS (
    SELECT 
        gcv.card_version_id,
        array_agg(gr.game_description ORDER BY gr.game_description) AS games
    FROM card_catalog.games_card_version gcv
    JOIN card_catalog.games_ref gr ON gcv.game_id = gr.game_id
    GROUP BY gcv.card_version_id
),
-- Promo types aggregated
promo_types_agg AS (
    SELECT 
        pc.card_version_id,
        array_agg(ptr.promo_type_desc ORDER BY ptr.promo_type_desc) AS promo_types
    FROM card_catalog.promo_card pc
    JOIN card_catalog.promo_types_ref ptr ON pc.promo_id = ptr.promo_id
    GROUP BY pc.card_version_id
),
-- Card stats pivoted
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
-- Illustrations with artists
illustrations_agg AS (
     SELECT
    cvi.card_version_id,
    jsonb_agg(
      jsonb_build_object(
        'illustration_id', cvi.illustration_id,
        'image_uris', i.image_uris,
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
-- Card faces aggregated
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
-- ✅ MAIN SELECT: Join everything together
SELECT 
    -- Primary IDs
    cv.card_version_id,
    cv.unique_card_id,
    ucr.card_name,
    
    -- Set information
    s.set_id,
    s.set_name,
    s.set_code,
    cv.collector_number,
    
    -- Card basics
    ucr.cmc,
    ucr.mana_cost,
    cv.oracle_text,
    ucr.reserved,
    
    -- Type information
    COALESCE(cta.types, ARRAY[]::text[]) AS types,
    COALESCE(cta.subtypes, ARRAY[]::text[]) AS subtypes,
    COALESCE(cta.supertypes, ARRAY[]::text[]) AS supertypes,
    
    -- Type line (constructed)
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
    
    -- Colors and identity
    COALESCE(ca.color_identity, ARRAY[]::text[]) AS color_identity,
    COALESCE(ka.keywords, ARRAY[]::text[]) AS keywords,
    
    -- Stats
    csa.power,
    csa.toughness,
    csa.loyalty,
    csa.defense,
    
    -- Rarity and visual
    rr.rarity_name,
    bcr.border_color_name,
    fr.frame_year,
    lr.layout_name,
    
    -- Flags
    cv.is_promo,
    cv.is_digital,
    cv.is_oversized,
    cv.full_art,
    cv.textless,
    cv.booster,
    cv.variation,
    cv.is_multifaced,
    
    -- Artist and illustration
    COALESCE(ia.illustrations, '[]'::jsonb) AS illustrations,
    
    -- Aggregated data
    COALESCE(la.legalities, '{}'::jsonb) AS legalities,
    COALESCE(ga.games, ARRAY[]::text[]) AS games,
    COALESCE(pta.promo_types, ARRAY[]::text[]) AS promo_types,
    COALESCE(cfa.card_faces, '[]'::jsonb) AS card_faces,
    
    -- Face count for quick reference
    CASE 
        WHEN cv.is_multifaced THEN jsonb_array_length(COALESCE(cfa.card_faces, '[]'::jsonb))--change the reference
        ELSE 1
    END AS face_count,
    
    -- Search helpers
    to_tsvector('english', 
        ucr.card_name || ' ' || 
        COALESCE(cv.oracle_text, '') || ' ' ||
        COALESCE(array_to_string(cta.types, ' '), '') || ' ' ||
        COALESCE(array_to_string(cta.subtypes, ' '), '') || ' ' ||
        COALESCE(array_to_string(ka.keywords, ' '), '')
    ) AS search_vector,
    
    -- Timestamps
    CURRENT_TIMESTAMP AS materialized_at

FROM card_catalog.card_version cv
JOIN card_catalog.unique_cards_ref ucr ON cv.unique_card_id = ucr.unique_card_id
JOIN card_catalog.sets s ON cv.set_id = s.set_id
JOIN card_catalog.rarities_ref rr ON cv.rarity_id = rr.rarity_id
JOIN card_catalog.border_color_ref bcr ON cv.border_color_id = bcr.border_color_id
JOIN card_catalog.frames_ref fr ON cv.frame_id = fr.frame_id
JOIN card_catalog.layouts_ref lr ON cv.layout_id = lr.layout_id

-- Join aggregated data
LEFT JOIN card_types_agg cta ON ucr.unique_card_id = cta.unique_card_id
LEFT JOIN colors_agg ca ON ucr.unique_card_id = ca.unique_card_id
LEFT JOIN keywords_agg ka ON ucr.unique_card_id = ka.unique_card_id
LEFT JOIN legalities_agg la ON ucr.unique_card_id = la.unique_card_id
LEFT JOIN games_agg ga ON cv.card_version_id = ga.card_version_id
LEFT JOIN promo_types_agg pta ON cv.card_version_id = pta.card_version_id
LEFT JOIN card_stats_agg csa ON cv.card_version_id = csa.card_version_id
LEFT JOIN illustrations_agg ia ON cv.card_version_id = ia.card_version_id
LEFT JOIN card_faces_agg cfa ON cv.card_version_id = cfa.card_version_id;

CREATE UNIQUE INDEX idx_v_card_versions_complete_pk ON card_catalog.v_card_versions_complete (card_version_id);
CREATE INDEX idx_v_card_versions_complete_name ON card_catalog.v_card_versions_complete (card_name);
CREATE INDEX idx_v_card_versions_complete_set ON card_catalog.v_card_versions_complete (set_name, collector_number);
CREATE INDEX idx_v_card_versions_complete_cmc ON card_catalog.v_card_versions_complete (cmc);
CREATE INDEX idx_v_card_versions_complete_colors ON card_catalog.v_card_versions_complete USING GIN (color_identity);
CREATE INDEX idx_v_card_versions_complete_types ON card_catalog.v_card_versions_complete USING GIN (types);
CREATE INDEX idx_v_card_versions_complete_rarity ON card_catalog.v_card_versions_complete (rarity_name);
CREATE INDEX idx_v_card_versions_complete_search ON card_catalog.v_card_versions_complete USING GIN (search_vector);
CREATE INDEX idx_v_card_versions_complete_legalities ON card_catalog.v_card_versions_complete USING GIN (legalities);


--STORED PROCEDURE---------------------------
CREATE OR REPLACE FUNCTION card_catalog.insert_full_card_version(
    p_card_name TEXT,
    p_cmc INT,
    p_mana_cost TEXT,
    p_reserved BOOLEAN,
    p_oracle_text TEXT,
    p_set_name TEXT,
    p_collector_number TEXT,
    p_rarity_name TEXT,
    p_border_color TEXT,
    p_frame_year TEXT,
    p_layout_name TEXT,
    p_is_promo BOOLEAN,

    p_is_digital BOOLEAN,
    p_keywords JSONB,
    p_colors JSONB,
    p_artist JSONB,
    p_artist_id JSONB,
    p_legalities JSONB,
    p_illustration_id UUID,
    p_types JSONB,
    p_supertypes JSONB,
    p_subtypes JSONB,
    p_games JSONB,
    p_oversized BOOLEAN, 
    p_booster BOOLEAN,
    p_full_art BOOLEAN,
    p_textless BOOLEAN,
    p_power TEXT,
    p_toughness TEXT,
    p_loyalty TEXT,--new
    p_defense TEXT,--new
    p_promo_types JSONB,
    p_variation BOOLEAN,
    p_card_faces JSONB,
    --new
    p_image_uris JSONB,
    --external ids
    p_scryfall_id UUID,
    p_oracle_id UUID,
    p_multiverse_ids JSONB,
    p_tcgplayer_id INT,
    p_tcgplayer_etched_id INT,
    p_cardmarket_id INT
)
RETURNS UUID AS $$
DECLARE
    v_unique_card_id UUID;
    v_set_id UUID;
    v_rarity_id INT;
    v_border_color_id INT;
    v_frame_id INT;
    v_layout_id INT;
    v_card_version_id UUID;
    v_color TEXT;
    v_color_id INT;
    v_legality_id INT;
    v_format_id INT;
    v_format TEXT;
    v_status TEXT;
    v_type TEXT;
    v_promo_type TEXT;
    v_promo_id INT;
    v_face JSONB;
    v_game TEXT;
    v_game_id INT;
    v_artist_name TEXT;
    v_artist_uuid UUID;
    v_illustration_id UUID;
    v_scryfall_id UUID;
    v_oracle_id UUID;
    v_multiverse_id INT;
    v_tcgplayer_id INT;
    v_tcgplayer_etched_id INT;
    v_cardmarket_id INT;
    v_keyword TEXT;
    v_keyword_id INT;
    v_card_faces_id UUID;
BEGIN
    -- Insert or retrieve unique card
    INSERT INTO card_catalog.unique_cards_ref (card_name, cmc, mana_cost, reserved)
    VALUES (p_card_name, p_cmc, p_mana_cost, p_reserved)
    ON CONFLICT (card_name) DO NOTHING;

    SELECT unique_card_id INTO v_unique_card_id
    FROM card_catalog.unique_cards_ref
    WHERE card_name = p_card_name;

    -- Set lookup — schema-qualified so unqualified resolution via
    -- search_path can't route us to a `public.sets` drift copy.
    SELECT set_id INTO v_set_id
    FROM card_catalog.sets
    WHERE set_name = p_set_name;
    IF v_set_id IS NULL THEN
    -- Use your MISSING_SET
        v_set_id := '00000000-0000-0000-0000-000000000002';
    END IF;


    -- Rarity
    SELECT rarity_id INTO v_rarity_id
    FROM card_catalog.rarities_ref
    WHERE rarity_name = p_rarity_name;

    IF v_rarity_id IS NULL THEN
        INSERT INTO card_catalog.rarities_ref (rarity_name) 
        VALUES (p_rarity_name)
        RETURNING rarity_id INTO v_rarity_id;
    END IF;

    -- Border
    SELECT border_color_id INTO v_border_color_id
    FROM card_catalog.border_color_ref
    WHERE border_color_name = p_border_color;

    IF v_border_color_id IS NULL THEN
        INSERT INTO card_catalog.border_color_ref (border_color_name) 
        VALUES (p_border_color)
        RETURNING border_color_id INTO v_border_color_id;
    END IF;

    -- Frame
    SELECT frame_id INTO v_frame_id
    FROM card_catalog.frames_ref
    WHERE frame_year = p_frame_year;

    IF v_frame_id IS NULL THEN
        INSERT INTO card_catalog.frames_ref (frame_year) 
        VALUES (p_frame_year)
        RETURNING frame_id INTO v_frame_id;
    END IF;

    -- Layout
    SELECT layout_id INTO v_layout_id
    FROM card_catalog.layouts_ref
    WHERE layout_name = p_layout_name;

    IF v_layout_id IS NULL THEN
        INSERT INTO card_catalog.layouts_ref (layout_name) 
        VALUES (p_layout_name)
        RETURNING layout_id INTO v_layout_id;
    END IF;
    --zip the arrays and insert types
   

    -- Card version

    INSERT INTO card_catalog.card_version (
        unique_card_id, oracle_text, set_id,
        collector_number, rarity_id, border_color_id,
        frame_id, layout_id, is_promo, is_digital,
        is_oversized, full_art, textless, booster,
        variation
    ) VALUES (
        v_unique_card_id, p_oracle_text, v_set_id,
        p_collector_number, v_rarity_id, v_border_color_id,
        v_frame_id, v_layout_id, p_is_promo, p_is_digital,
        p_oversized, p_full_art, p_textless, p_booster,
        p_variation
    )
    ON CONFLICT (unique_card_id, set_id, collector_number) DO NOTHING
    RETURNING card_version_id INTO v_card_version_id;

    IF v_card_version_id IS NULL THEN
    SELECT card_version_id
    INTO v_card_version_id
    FROM card_catalog.card_version
    WHERE unique_card_id = v_unique_card_id
        AND set_id = v_set_id
        AND collector_number = p_collector_number
    LIMIT 1;
    END IF;
    --add the ids

    -- Explicit conflict target = the PRIMARY KEY. This means:
    --   * Idempotent re-insert of (card_version_id, ref_id) is silently absorbed
    --     (safe to retry the proc against an already-loaded card_version).
    --   * UNIQUE (ref_id, value) violations no longer apply because that
    --     constraint was dropped (intentionally — see comment on the table).
    -- Previously this clause was a bare `ON CONFLICT DO NOTHING`, which
    -- silently absorbed UNIQUE-constraint violations and dropped one
    -- card_version row per shared tcgplayer_id / cardmarket_id pair.
    INSERT INTO card_catalog.card_external_identifier (card_identifier_ref_id, card_version_id, value)
    SELECT r.card_identifier_ref_id, v_card_version_id, n.value
    FROM (
        SELECT 'scryfall_id'        AS name, p_scryfall_id::text          AS value
        UNION ALL SELECT 'oracle_id',          p_oracle_id::text
        UNION ALL SELECT 'multiverse_id',      x::text FROM jsonb_array_elements_text(COALESCE(p_multiverse_ids, '[]'::jsonb)) AS x
        UNION ALL SELECT 'tcgplayer_id',       p_tcgplayer_id::text
        UNION ALL SELECT 'tcgplayer_etched_id',p_tcgplayer_etched_id::text
        UNION ALL SELECT 'cardmarket_id',      p_cardmarket_id::text
    ) AS n
    JOIN card_catalog.card_identifier_ref r
    ON r.identifier_name = n.name
    WHERE n.value IS NOT NULL
    ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING;


    --card stat
    INSERT INTO card_catalog.card_version_stats (card_version_id, stat_id, stat_value)
    SELECT v_card_version_id, stat_id, stat_value
    FROM (
        VALUES 
            ((SELECT stat_id FROM card_catalog.card_stats_ref WHERE stat_name = 'power'), p_power),
            ((SELECT stat_id FROM card_catalog.card_stats_ref WHERE stat_name = 'toughness'), p_toughness),
            ((SELECT stat_id FROM card_catalog.card_stats_ref WHERE stat_name = 'loyalty'), p_loyalty),
            ((SELECT stat_id FROM card_catalog.card_stats_ref WHERE stat_name = 'defense'), p_defense)
    ) AS stats(stat_id, stat_value)
    WHERE stat_value IS NOT NULL
    ON CONFLICT DO NOTHING;

    -- Promo types


    FOR v_promo_type IN SELECT jsonb_array_elements_text(p_promo_types) LOOP
        WITH existing AS (
            SELECT promo_id FROM card_catalog.promo_types_ref WHERE promo_type_desc = v_promo_type
        ),
        ins AS (
            INSERT INTO card_catalog.promo_types_ref (promo_type_desc)
            SELECT v_promo_type
            WHERE NOT EXISTS (SELECT 1 FROM existing)
            RETURNING promo_id
        )
        SELECT promo_id INTO v_promo_id
        FROM ins
        UNION ALL
        SELECT promo_id FROM existing
        LIMIT 1;

        INSERT INTO card_catalog.promo_card (promo_id, card_version_id)
        VALUES (v_promo_id, v_card_version_id)
        ON CONFLICT DO NOTHING;
    END LOOP;

 
    -- Type line handling
    IF p_card_faces IS NULL
    OR jsonb_typeof(p_card_faces) <> 'array'
    OR jsonb_array_length(p_card_faces) = 0 THEN
        FOR v_type IN SELECT jsonb_array_elements_text(p_supertypes) LOOP
            INSERT INTO card_catalog.card_types (unique_card_id, type_name, type_category)
            VALUES (v_unique_card_id, v_type, 'supertype')
            ON CONFLICT (unique_card_id, type_name) DO NOTHING;
        END LOOP;

        FOR v_type IN SELECT jsonb_array_elements_text(p_types) LOOP
            INSERT INTO card_catalog.card_types (unique_card_id, type_name, type_category)
            VALUES (v_unique_card_id, v_type, 'type')
            ON CONFLICT (unique_card_id, type_name) DO NOTHING;
        END LOOP;

        FOR v_type IN SELECT jsonb_array_elements_text(p_subtypes) LOOP
            INSERT INTO card_catalog.card_types (unique_card_id, type_name, type_category)
            VALUES (v_unique_card_id, v_type, 'subtype')
            ON CONFLICT (unique_card_id, type_name) DO NOTHING;
        END LOOP;

        -- ── Resolve single-faced artist ──────────────────────────
        -- Scryfall supplies both an artist UUID and a name. The rows
        -- in artists_ref are keyed by that Scryfall UUID, so we MUST
        -- ensure an artists_ref row exists for v_artist_uuid before
        -- the downstream FK on illustration_artist fires — otherwise
        -- every card on a fresh DB hits 23503 on its first sighting
        -- of each artist (~38k failures per import).
        --
        -- Mirrors the multi-faced branch below (line ~895) which
        -- already does this correctly. Fallback chain:
        --   1. Both UUID + name   → upsert keyed by UUID
        --   2. Name only, no UUID → upsert keyed by name
        --   3. Nothing            → "Unknown Artist" sentinel
        --                            (UUID '…001', seeded next to
        --                            artists_ref).
        v_artist_uuid := (p_artist_id ->> 0)::UUID;
        v_artist_name := p_artist ->> 0;

        IF v_artist_uuid IS NOT NULL AND v_artist_name IS NOT NULL THEN
            INSERT INTO card_catalog.artists_ref (artist_id, artist_name)
            VALUES (v_artist_uuid, v_artist_name)
            ON CONFLICT (artist_id) DO UPDATE
                SET updated_at = now()
            RETURNING artist_id INTO v_artist_uuid;
        ELSIF v_artist_name IS NOT NULL THEN
            INSERT INTO card_catalog.artists_ref (artist_name)
            VALUES (v_artist_name)
            ON CONFLICT (artist_name) DO UPDATE
                SET updated_at = now()
            RETURNING artist_id INTO v_artist_uuid;
        END IF;

        IF v_artist_uuid IS NULL THEN
            v_artist_uuid := '00000000-0000-0000-0000-000000000001'::uuid;
        END IF;

        -- Link illustration and artist for single-faced card.
        INSERT INTO card_catalog.illustrations (illustration_id, image_uris)
        VALUES (p_illustration_id, p_image_uris)
        ON CONFLICT (illustration_id)
        DO UPDATE SET
            image_uris = EXCLUDED.image_uris,
            updated_at = now()
        RETURNING illustration_id INTO v_illustration_id;

        INSERT INTO card_catalog.illustration_artist (illustration_id, artist_id)
        VALUES (p_illustration_id, v_artist_uuid)
        ON CONFLICT (illustration_id, artist_id) DO NOTHING;

        
        --card illustrations
        WITH exists AS (
            SELECT card_version_id, illustration_id
            FROM card_catalog.card_version_illustration
            WHERE card_version_id = v_card_version_id
                AND illustration_id = p_illustration_id
        )
        INSERT INTO card_catalog.card_version_illustration (card_version_id, illustration_id)
        SELECT v_card_version_id, p_illustration_id
        WHERE NOT EXISTS (SELECT 1 FROM exists);

    ELSE
        UPDATE card_catalog.card_version
        SET is_multifaced = true
        WHERE card_version_id = v_card_version_id;
        FOR v_face IN SELECT * FROM jsonb_array_elements(p_card_faces) LOOP
            v_artist_uuid := NULL;
            v_illustration_id := NULL;
            v_artist_name := NULL;
            v_card_faces_id := NULL;

            --insert the face
               -- Insert card face
            INSERT INTO card_catalog.card_faces (
                card_version_id, face_index, name, mana_cost,
                type_line, oracle_text, power, toughness, flavor_text
            ) VALUES (
                v_card_version_id,
                (v_face ->> 'face_index')::INT,
                v_face ->> 'name',
                v_face ->> 'mana_cost',
                v_face ->> 'type_line',
                v_face ->> 'oracle_text',
                v_face ->> 'power',
                v_face ->> 'toughness',
                v_face ->> 'flavor_text'
            )
            ON CONFLICT DO NOTHING--check whqat the conflict is 
            RETURNING card_faces_id INTO v_card_faces_id;

            if v_card_faces_id IS NULL THEN
                SELECT card_faces_id INTO v_card_faces_id
                FROM card_catalog.card_faces
                WHERE card_version_id = v_card_version_id
                    AND face_index = (v_face ->> 'face_index')::INT
                LIMIT 1;
            END IF;

            IF v_face ->> 'illustration_id' IS NOT NULL AND v_face ->> 'artist_id' IS NOT NULL THEN
                v_illustration_id := (v_face ->> 'illustration_id')::UUID;
                v_artist_uuid := (v_face ->> 'artist_id')::UUID;
                v_artist_name := (v_face ->> 'artist')::TEXT;

                INSERT INTO card_catalog.artists_ref (artist_id, artist_name)
                VALUES (v_artist_uuid, v_artist_name)
                ON CONFLICT DO NOTHING;

                INSERT INTO card_catalog.illustrations (illustration_id)
                VALUES (v_illustration_id)
                ON CONFLICT DO NOTHING;

                INSERT INTO card_catalog.illustration_artist (illustration_id, artist_id)
                VALUES (v_illustration_id, v_artist_uuid)
                ON CONFLICT DO NOTHING;

                --INSERT INTO card_catalog.card_version_illustration (card_version_id, illustration_id)
                --VALUES (v_card_version_id, v_illustration_id)
                INSERT INTO card_catalog.face_illustration (face_id, illustration_id)
                VALUES  (v_card_faces_id , v_illustration_id)
                ON CONFLICT DO NOTHING;
            END IF;


            -- Face-level types
            FOR v_type IN SELECT jsonb_array_elements_text(v_face -> 'supertypes') LOOP
                INSERT INTO card_catalog.card_types (unique_card_id, type_name, type_category)
                VALUES (v_unique_card_id, v_type, 'supertype')
                ON CONFLICT (unique_card_id, type_name) DO NOTHING;
            END LOOP;

            FOR v_type IN SELECT jsonb_array_elements_text(v_face -> 'types') LOOP
                INSERT INTO card_catalog.card_types (unique_card_id, type_name, type_category)
                VALUES (v_unique_card_id, v_type, 'type')
                ON CONFLICT (unique_card_id, type_name) DO NOTHING;
            END LOOP;

            FOR v_type IN SELECT jsonb_array_elements_text(v_face -> 'subtypes') LOOP
                INSERT INTO card_catalog.card_types (unique_card_id, type_name, type_category)
                VALUES (v_unique_card_id, v_type, 'subtype')
                ON CONFLICT (unique_card_id, type_name) DO NOTHING;
            END LOOP;
        END LOOP;
    END IF;

    -- Games
    FOR v_game IN SELECT jsonb_array_elements_text(p_games) LOOP
        INSERT INTO card_catalog.games_ref (game_description) VALUES (v_game)
        ON CONFLICT DO NOTHING;
        SELECT game_id INTO v_game_id FROM card_catalog.games_ref WHERE game_description = v_game;
        INSERT INTO card_catalog.games_card_version (card_version_id, game_id)
        VALUES (v_card_version_id, v_game_id)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- Colors
    FOR v_color IN SELECT jsonb_array_elements_text(p_colors) LOOP
        INSERT INTO card_catalog.colors_ref (color_name) VALUES (v_color)
        ON CONFLICT DO NOTHING;
        SELECT color_id INTO v_color_id FROM card_catalog.colors_ref WHERE color_name = v_color;
        INSERT INTO card_catalog.card_color_identity (unique_card_id, color_id)
        VALUES (v_unique_card_id, v_color_id)
        ON CONFLICT DO NOTHING;
    END LOOP;
    -- Keywords
    FOR v_keyword IN SELECT jsonb_array_elements_text(p_keywords) LOOP
            -- Insert keyword if not exists
            INSERT INTO card_catalog.keywords_ref (keyword_name)
            VALUES (v_keyword)
            ON CONFLICT (keyword_name) DO NOTHING
            RETURNING keyword_id INTO v_keyword_id;

            -- If keyword already existed, get its ID
            IF v_keyword_id IS NULL THEN
                SELECT keyword_id INTO v_keyword_id 
                FROM card_catalog.keywords_ref 
            WHERE keyword_name = v_keyword;
        END IF;

        -- Link keyword to unique card
        INSERT INTO card_catalog.card_keyword (unique_card_id, keyword_id)
        VALUES (v_unique_card_id, v_keyword_id)
        ON CONFLICT (unique_card_id, keyword_id) DO NOTHING;
    END LOOP;

    -- Legalities
    FOR v_format, v_status IN SELECT * FROM jsonb_each_text(p_legalities) LOOP
        IF v_status != 'not_legal' THEN
            INSERT INTO card_catalog.legal_status_ref (legal_status) VALUES (v_status)
            ON CONFLICT DO NOTHING;

            SELECT legality_id INTO v_legality_id FROM card_catalog.legal_status_ref WHERE legal_status = v_status;

            INSERT INTO card_catalog.formats_ref (format_name) VALUES (v_format)
            ON CONFLICT DO NOTHING;

            SELECT format_id INTO v_format_id FROM card_catalog.formats_ref WHERE format_name = v_format;

            INSERT INTO card_catalog.legalities (unique_card_id, format_id, legality_id)
            VALUES (v_unique_card_id, v_format_id, v_legality_id)
            ON CONFLICT DO NOTHING;
        END IF;
    END LOOP;

    RETURN v_card_version_id;
END;
$$ LANGUAGE plpgsql;
------------------------------------------------
CREATE OR REPLACE FUNCTION card_catalog.insert_batch_card_versions(
    p_cards JSONB  -- Array of card objects
)
RETURNS TABLE (
    total_processed INT,
    successful_inserts INT,
    failed_inserts INT,
    skipped_inserts INT,
    inserted_card_ids UUID[],
    error_details JSONB
) AS $$
DECLARE
    v_card JSONB;
    v_result UUID;
    v_total_processed INT := 0;
    v_successful_inserts INT := 0;
    v_failed_inserts INT := 0;
    v_skipped_inserts INT := 0;
    v_inserted_ids UUID[] := ARRAY[]::UUID[];
    v_error_details JSONB := '[]'::JSONB;
    v_error_info JSONB;
BEGIN
    -- Process each card in the batch
    FOR v_card IN SELECT * FROM jsonb_array_elements(p_cards)
    LOOP
        v_total_processed := v_total_processed + 1;
        
        BEGIN
            -- Call your existing function
            SELECT card_catalog.insert_full_card_version(
                v_card ->> 'card_name',
                (v_card ->> 'cmc')::NUMERIC::INT,
                v_card ->> 'mana_cost',
                (v_card ->> 'reserved')::BOOLEAN,
                v_card ->> 'oracle_text',
                v_card ->> 'set_name',
                v_card ->> 'collector_number',
                v_card ->> 'rarity_name',
                v_card ->> 'border_color',
                v_card ->> 'frame_year',
                v_card ->> 'layout_name',
                (v_card ->> 'is_promo')::BOOLEAN,
                (v_card ->> 'is_digital')::BOOLEAN,
                v_card -> 'keywords',
                v_card -> 'colors',
                v_card -> 'artist',
                v_card -> 'artist_ids',
                v_card -> 'legalities',
                (v_card ->> 'illustration_id')::UUID,
                v_card -> 'types',
                v_card -> 'supertypes',
                v_card -> 'subtypes',
                v_card -> 'games',
                (v_card ->> 'oversized')::BOOLEAN,
                (v_card ->> 'booster')::BOOLEAN,
                (v_card ->> 'full_art')::BOOLEAN,
                (v_card ->> 'textless')::BOOLEAN,
                v_card ->> 'power',
                v_card ->> 'toughness',
                v_card ->> 'loyalty',
                v_card ->> 'defense',
                v_card -> 'promo_types',
                (v_card ->> 'variation')::BOOLEAN,
                v_card -> 'card_faces',
                v_card -> 'image_uris',
                (v_card ->> 'scryfall_id')::UUID,
                (v_card ->> 'oracle_id')::UUID,
                v_card -> 'multiverse_ids',
                (v_card ->> 'tcgplayer_id')::INT,
                (v_card ->> 'tcgplayer_etched_id')::INT,
                (v_card ->> 'cardmarket_id')::INT
            ) INTO v_result;
            
            -- Success
            v_successful_inserts := v_successful_inserts + 1;
            v_inserted_ids := array_append(v_inserted_ids, v_result);
            
        EXCEPTION
            WHEN unique_violation THEN
                IF SQLERRM LIKE '%card_version_unique_card_id_set_id_collector_number_key%' THEN
                    -- Skipped (already exists)
                    v_skipped_inserts := v_skipped_inserts + 1;
                ELSE
                    v_failed_inserts := v_failed_inserts + 1;
                    v_error_info := jsonb_build_object(
                        'card_name', v_card ->> 'card_name',
                        'error_code', SQLSTATE,
                        'error_message', SQLERRM,
                        'card_index', v_total_processed
                    );
                    v_error_details := v_error_details || jsonb_build_array(v_error_info);
                END IF;
            WHEN OTHERS THEN
                v_failed_inserts := v_failed_inserts + 1;
                v_error_info := jsonb_build_object(
                    'card_name', v_card ->> 'card_name',
                    'error_code', SQLSTATE,
                    'error_message', SQLERRM,
                    'card_index', v_total_processed
                );
                v_error_details := v_error_details || jsonb_build_array(v_error_info);
        END;
    END LOOP;
    
    -- Return summary
    RETURN QUERY SELECT 
        v_total_processed::INT,
        v_successful_inserts::INT, 
        v_failed_inserts::INT,
        v_skipped_inserts::INT,
        v_inserted_ids::UUID[],
        v_error_details::JSONB;
END;
$$ LANGUAGE plpgsql;

/*
CREATE INDEX idx_card_types_category ON card_types (type_category);
CREATE INDEX idx_card_types_name ON card_types (type_name);
*/

CREATE OR REPLACE FUNCTION card_catalog.refresh_card_versions_complete()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY card_catalog.v_card_versions_complete;
    
    -- Log refresh
    RAISE NOTICE 'Materialized view v_card_versions_complete refreshed at %', now();
END;
$$ LANGUAGE plpgsql;

-- ✅ AUTO REFRESH: Trigger function to auto-refresh on data changes
CREATE OR REPLACE FUNCTION card_catalog.trigger_refresh_card_versions()
RETURNS trigger AS $$
BEGIN
    -- Schedule refresh (you might want to implement a queue system for production)
    PERFORM pg_notify('refresh_card_view', 'card_data_changed');
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_card_version_refresh 
    AFTER INSERT OR UPDATE OR DELETE ON card_catalog.card_version
    FOR EACH ROW EXECUTE FUNCTION card_catalog.trigger_refresh_card_versions();

CREATE TRIGGER tr_unique_cards_refresh 
    AFTER INSERT OR UPDATE OR DELETE ON card_catalog.unique_cards_ref
    FOR EACH ROW EXECUTE FUNCTION card_catalog.trigger_refresh_card_versions();

    -- ✅ HELPER VIEWS: Additional views for common queries

-- Quick card lookup by name
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

-- Latest version of each card
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

-- Cards by set statistics
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

-- ============================================================
-- Objects relocated from 01_set_schema.sql
-- ============================================================
-- These views + indexes depend on card_catalog.card_version, which is
-- defined in this file. They used to live at the top of file 01 and
-- broke replay (mat-view bodies are validated at create time, so the
-- forward reference to card_version failed).

DROP VIEW IF EXISTS card_catalog.v_joined_set;

CREATE VIEW card_catalog.v_joined_set
    (set_id, set_name, set_code, set_type, nonfoil_only, foil_only,
     card_count, released_at, digital, parent_set) AS
SELECT s.set_id, s.set_name, s.set_code, stl.set_type,
       s.nonfoil_only, s.foil_only,
       COUNT(cv.set_id) AS card_count,
       s.released_at, s.digital, ss.set_name
FROM card_catalog.sets s
LEFT JOIN card_catalog.sets ss ON s.parent_set = ss.set_id
JOIN card_catalog.set_type_list_ref stl ON s.set_type_id = stl.set_type_id
JOIN card_catalog.card_version cv ON cv.set_id = s.set_id
WHERE s.is_active = TRUE
GROUP BY s.set_id, s.set_name, s.set_code, stl.set_type,
         s.nonfoil_only, s.foil_only, s.released_at, s.digital, ss.set_name;

CREATE MATERIALIZED VIEW IF NOT EXISTS card_catalog.v_joined_set_materialized
    (set_id, set_name, set_code, set_type, card_count, released_at, digital) AS
SELECT s.set_id, s.set_name, s.set_code, stl.set_type,
       COUNT(cv.set_id) AS card_count,
       s.released_at, s.digital
FROM card_catalog.sets s
JOIN card_catalog.set_type_list_ref stl ON s.set_type_id = stl.set_type_id
JOIN card_catalog.card_version cv ON cv.set_id = s.set_id
GROUP BY s.set_id, s.set_name, s.set_code, stl.set_type, s.released_at, s.digital;

-- Speeds up the JOIN between card_version and sets used by the view above.
CREATE INDEX IF NOT EXISTS idx_card_version_set_id
    ON card_catalog.card_version(set_id);

CREATE INDEX IF NOT EXISTS idx_v_joined_set_materialized_set_code
    ON card_catalog.v_joined_set_materialized(set_code);

-- INSTEAD OF INSERT trigger — relocated here from 01_set_schema.sql.
-- The trigger function `card_catalog.trigger_insert_on_joined_set`
-- is still defined in file 01 (function bodies are lazy), but the
-- trigger attachment has to happen after the view exists.
DROP TRIGGER IF EXISTS trg_insert_joined_set ON card_catalog.v_joined_set;
CREATE TRIGGER trg_insert_joined_set
INSTEAD OF INSERT ON card_catalog.v_joined_set
FOR EACH ROW EXECUTE FUNCTION card_catalog.trigger_insert_on_joined_set();

COMMIT;