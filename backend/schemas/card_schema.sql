CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS unique_cards (
    unique_card_id UUID PRIMARY KEY,
    card_name VARCHAR(100) NOT NULL UNIQUE,
    cmc int,
    mana_cost VARCHAR(50),
    reserved BOOL DEFAULT(false),
    is_multifaced BOOL DEFAULT(false),
    other_face_id UUID DEFAULT(NULL)
);

CREATE TABLE IF NOT EXISTS border_color (
    border_color_id SERIAL PRIMARY KEY, 
    border_color VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS card_types (
    unique_card_id UUID NOT NULL REFERENCES unique_cards(unique_card_id) ON DELETE CASCADE,
    type_name VARCHAR(20) NOT NULL,
    type_category TEXT CHECK (type_category IN ('type', 'subtype', 'supertype')),
    PRIMARY KEY (unique_card_id, type_name)
);

CREATE TABLE IF NOT EXISTS rarities (
    rarity_id SERIAL PRIMARY KEY,
    rarity_name VARCHAR(20) UNIQUE NOT NULL
);


CREATE TABLE IF NOT EXISTS artists (
    artist_id uuid PRIMARY KEY,
    artist_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS frames (
    frame_id SERIAL PRIMARY KEY,
    frame_year VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS layouts (
    layout_id SERIAL PRIMARY KEY,
    layout_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS keyword_list (
    keyword_id SERIAL PRIMARY KEY,
    keyword_name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS card_keyword (
    unique_card_id UUID REFERENCES unique_cards(unique_card_id) ON DELETE CASCADE,
    keyword_id INT NOT NULL REFERENCES keyword_list(keyword_id) ON DELETE CASCADE,
    PRIMARY KEY (unique_card_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS color_list (
    color_id SERIAL PRIMARY KEY,
    color_name VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS color_produced (
    unique_card_id UUID REFERENCES unique_cards(unique_card_id) ON DELETE CASCADE,
    color_id int NOT NULL REFERENCES color_list(color_id) ON DELETE CASCADE,
    PRIMARY KEY (unique_card_id, color_id)
);

CREATE TABLE IF NOT EXISTS card_color_identity (
    unique_card_id UUID REFERENCES unique_cards(unique_card_id) ON DELETE CASCADE,
    color_id int NOT NULL REFERENCES color_list(color_id) ON DELETE CASCADE,
    PRIMARY KEY (unique_card_id, color_id)
);


CREATE TABLE IF NOT EXISTS formats_list (
    format_id SERIAL PRIMARY KEY,
    format_name VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS legal_status (
    legality_id SERIAL PRIMARY KEY, 
    legal_status VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS legalities (
    unique_card_id UUID REFERENCES unique_cards(unique_card_id) ON DELETE CASCADE,
    format_id INT NOT NULL REFERENCES formats_list(format_id) ON DELETE CASCADE,
    legality_id INT NOT NULL REFERENCES legal_status(legality_id) ON DELETE CASCADE,
    PRIMARY KEY(unique_card_id, format_id)
);



CREATE TABLE IF NOT EXISTS card_version (
    card_version_id UUID PRIMARY KEY,
    unique_card_id UUID NOT NULL REFERENCES unique_cards(unique_card_id) ON DELETE CASCADE,
    image_uri int UNIQUE,
    oracle_text TEXT,
    set_id UUID NOT NULL REFERENCES sets(set_id),
    collector_number int,
    rarity_id INT NOT NULL REFERENCES rarities(rarity_id) ON DELETE CASCADE,
    border_color_id INT NOT NULL REFERENCES border_color(border_color_id) ON DELETE CASCADE,
    frame_id int NOT NULL REFERENCES frames(frame_id) ON DELETE CASCADE,
    layout_id INT NOT NULL REFERENCES layouts(layout_id) ON DELETE CASCADE, 
    is_promo BOOL DEFAULT false, 
    is_digital BOOL DEFAULT false
);

CREATE TABLE IF NOT EXISTS illustrations (
    card_version_id uuid NOT NULL REFERENCES card_version(card_version_id) ON DELETE CASCADE,
    illustration_id uuid NOT NULL UNIQUE,
    artist_id uuid NOT NULL REFERENCES artists(artist_id) ON DELETE CASCADE,
    PRIMARY KEY (card_version_id, illustration_id)
);



/*
CREATE INDEX idx_card_types_category ON card_types (type_category);
CREATE INDEX idx_card_types_name ON card_types (type_name);
*/
