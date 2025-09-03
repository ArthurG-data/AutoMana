CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- TABLES------------------------------------

CREATE TABLE IF NOT EXISTS unique_cards_ref (
    unique_card_id UUID PRIMARY KEY DEFAULT uuid_generate_v4() ON DELETE CASCADE,
    card_name TEXT NOT NULL UNIQUE,
    cmc INT,
    mana_cost VARCHAR(50),
    reserved BOOL DEFAULT(false),
    is_multifaced BOOL DEFAULT(false),
    other_face_id UUID DEFAULT(NULL)
);

CREATE TABLE IF NOT EXISTS border_color_ref (
    border_color_id SERIAL PRIMARY KEY, 
    border_color_name VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS card_types (
    unique_card_id UUID NOT NULL REFERENCES unique_cards_ref(unique_card_id) ON DELETE CASCADE,
    type_name VARCHAR(20) NOT NULL,
    type_category TEXT CHECK (type_category IN ('type', 'subtype', 'supertype')),
    PRIMARY KEY (unique_card_id, type_name)
);


CREATE TABLE IF NOT EXISTS rarities_ref (
    rarity_id SERIAL PRIMARY KEY,
    rarity_name VARCHAR(20) UNIQUE NOT NULL
);


CREATE TABLE IF NOT EXISTS artists_ref (
    artist_id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    artist_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS frames_ref (
    frame_id SERIAL PRIMARY KEY,
    frame_year VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS layouts_ref (
    layout_id SERIAL PRIMARY KEY,
    layout_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS keywords_ref (
    keyword_id SERIAL PRIMARY KEY,
    keyword_name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS card_keyword (
    unique_card_id UUID REFERENCES unique_cards_ref(unique_card_id) ON DELETE CASCADE,
    keyword_id INT NOT NULL REFERENCES keywords_ref(keyword_id) ON DELETE CASCADE,
    PRIMARY KEY (unique_card_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS colors_ref (
    color_id SERIAL PRIMARY KEY,
    color_name VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS color_produced (
    unique_card_id UUID REFERENCES unique_cards_ref(unique_card_id) ON DELETE CASCADE,
    color_id int NOT NULL REFERENCES colors_ref(color_id) ON DELETE CASCADE,
    PRIMARY KEY (unique_card_id, color_id)
);

CREATE TABLE IF NOT EXISTS card_color_identity (
    unique_card_id UUID REFERENCES unique_cards_ref(unique_card_id) ON DELETE CASCADE,
    color_id int NOT NULL REFERENCES colors_ref(color_id) ON DELETE CASCADE,
    PRIMARY KEY (unique_card_id, color_id)
);


CREATE TABLE IF NOT EXISTS formats_ref (
    format_id SERIAL PRIMARY KEY,
    format_name VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS legal_status_ref (
    legality_id SERIAL PRIMARY KEY, 
    legal_status VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS legalities (
    unique_card_id UUID REFERENCES unique_cards_ref(unique_card_id) ON DELETE CASCADE,
    format_id INT NOT NULL REFERENCES formats_ref(format_id) ON DELETE CASCADE,
    legality_id INT NOT NULL REFERENCES legal_status_ref(legality_id) ON DELETE CASCADE,
    PRIMARY KEY(unique_card_id, format_id)
);

CREATE TABLE IF NOT EXISTS card_version (
    card_version_id UUID PRIMARY KEY DEFAULT uuid_generate_v4() ON DELETE CASCADE,
    unique_card_id UUID NOT NULL REFERENCES unique_cards_ref(unique_card_id) ON DELETE CASCADE,
    oracle_text TEXT,
    set_id UUID NOT NULL REFERENCES sets(set_id),
    collector_number VARCHAR(50),
    rarity_id INT NOT NULL REFERENCES rarities_ref(rarity_id) ON DELETE CASCADE,
    border_color_id INT NOT NULL REFERENCES border_color_ref(border_color_id) ON DELETE CASCADE,
    frame_id int NOT NULL REFERENCES frames_ref(frame_id) ON DELETE CASCADE,
    layout_id INT NOT NULL REFERENCES layouts_ref(layout_id) ON DELETE CASCADE, 
    is_promo BOOL DEFAULT false, 
    is_digital BOOL DEFAULT false,
    is_oversized BOOL DEFAULT false,
);


CREATE TABLE IF NOT EXISTS illustrations (
    illustration_id UUID PRIMARY KEY, 
    file_uri TEXT,
    added_on TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS illustration_artist (
    illustration_id uuid PRIMARY KEY REFERENCES illustrations(illustration_id) ON DELETE CASCADE,
    artist_id uuid NOT NULL REFERENCES artists_ref(artist_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS card_version_illustration (
    card_version_id UUID PRIMARY KEY REFERENCES card_version(card_version_id) ON DELETE CASCADE,
    illustration_id UUID NOT NULL
);

--need to be added

CREATE TABLE IF NOT EXISTS games_ref (
    game_id SERIAL PRIMARY KEY,
    game_description  VARCHAR(20) NOT NULL UNIQUE 
);

CREATE TABLE IF NOT EXISTS games_card_version (
    game_id INT NOT NULL REFERENCES games_ref(game_id),
    card_version_id UUID NOT NULL REFERENCES card_version(card_version_id),
    PRIMARY KEY (game_id, card_version_id)
);
CREATE TABLE IF NOT EXISTS promo_types_ref (
    promo_id SERIAL PRIMARY KEY,
    promo_type_desc TEXT UNIQUE NOT NULL 
);

CREATE TABLE IF NOT EXISTS promo_card (
    promo_id INT NOT NULL REFERENCES promo_types_ref(promo_id),
    card_version_id UUID NOT NULL REFERENCES card_version(card_version_id),
	PRIMARY KEY (promo_id, card_version_id)
);

CREATE TABLE IF NOT EXISTS card_faces (
    card_faces_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    card_version_id UUID NOT NULL REFERENCES card_version(card_version_id),
    face_index INT,
    name TEXT NOT NULL,
    mana_cost TEXT,
    type_line TEXT NOT NULL,
    oracle_text TEXT,
    power TEXT,
    toughness TEXT,
    flavor_text TEXT
);



--VIEWS -------------------------------------
CREATE OR REPLACE VIEW card_version_count AS
SELECT
    uc.card_id,
    uc.name,
    COUNT(cv.version_id) AS version_count
FROM unique_card uc
LEFT JOIN card_version cv ON uc.card_id = cv.card_id
GROUP BY uc.card_id, uc.name;

--STORED PROCEDURE---------------------------
CREATE OR REPLACE FUNCTION insert_full_card_version(
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
    p_colors JSONB,
    p_artist TEXT,
    p_artist_id TEXT,
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
    p_promo_types JSONB,
    p_variation BOOLEAN,
    p_card_faces JSONB
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
BEGIN
    -- Insert or retrieve unique card
    INSERT INTO unique_cards_ref (card_name, cmc, mana_cost, reserved)
    VALUES (p_card_name, p_cmc, p_mana_cost, p_reserved)
    ON CONFLICT (card_name) DO NOTHING;

    SELECT unique_card_id INTO v_unique_card_id
    FROM unique_cards_ref
    WHERE card_name = p_card_name;

    -- Set lookup
    SELECT set_id INTO v_set_id
    FROM sets
    WHERE set_name = p_set_name;
    IF v_set_id IS NULL THEN
    -- Use your MISSING_SET
        v_set_id := '00000000-0000-0000-0000-000000000002';
    END IF;
    -- Rarity
    INSERT INTO rarities_ref (rarity_name) VALUES (p_rarity_name)
    ON CONFLICT DO NOTHING;
    SELECT rarity_id INTO v_rarity_id FROM rarities_ref WHERE rarity_name = p_rarity_name;

    -- Border
    INSERT INTO border_color_ref (border_color_name) VALUES (p_border_color)
    ON CONFLICT DO NOTHING;
    SELECT border_color_id INTO v_border_color_id FROM border_color_ref WHERE border_color_name = p_border_color;

    -- Frame
    INSERT INTO frames_ref (frame_year) VALUES (p_frame_year)
    ON CONFLICT DO NOTHING;
    SELECT frame_id INTO v_frame_id FROM frames_ref WHERE frame_year = p_frame_year;

    -- Layout
    INSERT INTO layouts_ref (layout_name) VALUES (p_layout_name)
    ON CONFLICT DO NOTHING;
    SELECT layout_id INTO v_layout_id FROM layouts_ref WHERE layout_name = p_layout_name;

    -- Artist
    INSERT INTO artists_ref (artist_id, artist_name) VALUES (p_artist_id, p_artist)
    ON CONFLICT DO NOTHING;

    -- Illustration
    INSERT INTO illustrations (illustration_id)
    VALUES (p_illustration_id)
    ON CONFLICT DO NOTHING;

    INSERT INTO illustration_artist (illustration_id, artist_id)
    VALUES (p_illustration_id, p_artist_id)
    ON CONFLICT DO NOTHING;

    -- Card version
    INSERT INTO card_version (
        unique_card_id, oracle_text, set_id,
        collector_number, rarity_id, border_color_id,
        frame_id, layout_id, is_promo, is_digital,
        oversized, full_art, textless, booster,
        variation, power, toughness
    ) VALUES (
        v_unique_card_id, p_oracle_text, v_set_id,
        p_collector_number, v_rarity_id, v_border_color_id,
        v_frame_id, v_layout_id, p_is_promo, p_is_digital,
        p_oversized, p_full_art, p_textless, p_booster,
        p_variation, p_power, p_toughness
    )
    RETURNING card_version_id INTO v_card_version_id;

    INSERT INTO card_version_illustration (card_version_id, illustration_id)
    VALUES (v_card_version_id, p_illustration_id)
    ON CONFLICT DO NOTHING;

    -- Promo types
    FOR v_promo_type IN SELECT jsonb_array_elements_text(p_promo_types)
    LOOP
        INSERT INTO promo_types_ref (promo_type_desc) VALUES (v_promo_type)
        ON CONFLICT DO NOTHING;
        SELECT promo_id INTO v_promo_id FROM promo_types_ref WHERE promo_type_desc = v_promo_type;
        INSERT INTO promo_card(promo_id, card_version_id)
        VALUES (v_promo_id, v_card_version_id)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- Type line handling
    IF p_card_faces IS NULL
    OR jsonb_typeof(p_card_faces) <> 'array'
    OR jsonb_array_length(p_card_faces) = 0 THEN
        FOR v_type IN SELECT jsonb_array_elements_text(p_supertypes) LOOP
            INSERT INTO card_types (unique_card_id, type_name, type_category)
            VALUES (v_unique_card_id, v_type, 'supertype')
            ON CONFLICT (unique_card_id, type_name) DO NOTHING;
        END LOOP;

        FOR v_type IN SELECT jsonb_array_elements_text(p_types) LOOP
            INSERT INTO card_types (unique_card_id, type_name, type_category)
            VALUES (v_unique_card_id, v_type, 'type')
            ON CONFLICT (unique_card_id, type_name) DO NOTHING;
        END LOOP;

        FOR v_type IN SELECT jsonb_array_elements_text(p_subtypes) LOOP
            INSERT INTO card_types (unique_card_id, type_name, type_category)
            VALUES (v_unique_card_id, v_type, 'subtype')
            ON CONFLICT (unique_card_id, type_name) DO NOTHING;
        END LOOP;
    ELSE
        FOR v_face IN SELECT * FROM jsonb_array_elements(p_card_faces) LOOP
            v_artist_uuid := NULL;
            v_illustration_id := NULL;
            v_artist_name := NULL;

            IF v_face ->> 'illustration_id' IS NOT NULL AND v_face ->> 'artist_id' IS NOT NULL THEN
                v_illustration_id := (v_face ->> 'illustration_id')::UUID;
                v_artist_uuid := (v_face ->> 'artist_id')::UUID;
                v_artist_name := (v_face ->> 'artist')::TEXT;

                INSERT INTO artists_ref (artist_id, artist_name)
                VALUES (v_artist_uuid, v_artist_name)
                ON CONFLICT DO NOTHING;

                INSERT INTO illustrations (illustration_id)
                VALUES (v_illustration_id)
                ON CONFLICT DO NOTHING;

                INSERT INTO illustration_artist (illustration_id, artist_id)
                VALUES (v_illustration_id, v_artist_uuid)
                ON CONFLICT DO NOTHING;

                INSERT INTO card_version_illustration (card_version_id, illustration_id)
                VALUES (v_card_version_id, v_illustration_id)
                ON CONFLICT DO NOTHING;
            END IF;

            -- Insert card face
            INSERT INTO card_faces (
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
            );

            -- Face-level types
            FOR v_type IN SELECT jsonb_array_elements_text(v_face -> 'supertypes') LOOP
                INSERT INTO card_types (unique_card_id, type_name, type_category)
                VALUES (v_unique_card_id, v_type, 'supertype')
                ON CONFLICT (unique_card_id, type_name) DO NOTHING;
            END LOOP;

            FOR v_type IN SELECT jsonb_array_elements_text(v_face -> 'types') LOOP
                INSERT INTO card_types (unique_card_id, type_name, type_category)
                VALUES (v_unique_card_id, v_type, 'type')
                ON CONFLICT (unique_card_id, type_name) DO NOTHING;
            END LOOP;

            FOR v_type IN SELECT jsonb_array_elements_text(v_face -> 'subtypes') LOOP
                INSERT INTO card_types (unique_card_id, type_name, type_category)
                VALUES (v_unique_card_id, v_type, 'subtype')
                ON CONFLICT (unique_card_id, type_name) DO NOTHING;
            END LOOP;
        END LOOP;
    END IF;

    -- Games
    FOR v_game IN SELECT jsonb_array_elements_text(p_games) LOOP
        INSERT INTO games_ref (game_description) VALUES (v_game)
        ON CONFLICT DO NOTHING;
        SELECT game_id INTO v_game_id FROM games_ref WHERE game_description = v_game;
        INSERT INTO games_card_version (card_version_id, game_id)
        VALUES (v_card_version_id, v_game_id)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- Colors
    FOR v_color IN SELECT jsonb_array_elements_text(p_colors) LOOP
        INSERT INTO colors_ref (color_name) VALUES (v_color)
        ON CONFLICT DO NOTHING;
        SELECT color_id INTO v_color_id FROM colors_ref WHERE color_name = v_color;
        INSERT INTO card_color_identity (unique_card_id, color_id)
        VALUES (v_unique_card_id, v_color_id)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- Legalities
    FOR v_format, v_status IN SELECT * FROM jsonb_each_text(p_legalities) LOOP
        IF v_status != 'not_legal' THEN
            INSERT INTO legal_status_ref (legal_status) VALUES (v_status)
            ON CONFLICT DO NOTHING;

            SELECT legality_id INTO v_legality_id FROM legal_status_ref WHERE legal_status = v_status;

            INSERT INTO formats_ref (format_name) VALUES (v_format)
            ON CONFLICT DO NOTHING;

            SELECT format_id INTO v_format_id FROM formats_ref WHERE format_name = v_format;

            INSERT INTO legalities (unique_card_id, format_id, legality_id)
            VALUES (v_unique_card_id, v_format_id, v_legality_id)
            ON CONFLICT DO NOTHING;
        END IF;
    END LOOP;

    RETURN v_card_version_id;
END;
$$ LANGUAGE plpgsql;


/*
CREATE INDEX idx_card_types_category ON card_types (type_category);
CREATE INDEX idx_card_types_name ON card_types (type_name);
*/
