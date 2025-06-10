CREATE TABLE IF NOT EXISTS set_type_list_ref(
    set_type_id SERIAL NOT NULL PRIMARY KEY,
    set_type VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS sets(
    set_id UUID NOT NULL PRIMARY KEY DEFAULT uuid_generate_v4(),
    set_name VARCHAR(100) UNIQUE NOT NULL,
    set_code VARCHAR(10) UNIQUE NOT NULL,
    set_type_id INT NOT NULL REFERENCES set_type_list_ref(set_type_id),
    released_at DATE NOT NULL,
    digital BOOL DEFAULT FALSE,
    nonfoil_only BOOL DEFAULT FALSE,
    foil_only BOOL DEFAULT FALSE,
    parent_set UUID DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS icon_query_ref(
    icon_query_id SERIAL PRIMARY KEY,
    icon_query_uri VARCHAR(10) UNIQUE NOT NULL
);

CREATE TABLE  IF NOT EXISTS icon_set(
    icon_query_id INT REFERENCES icon_query_ref(icon_query_id),
    set_id UUID REFERENCES sets(set_id) UNIQUE,
    PRIMARY KEY (icon_query_id, set_id)
);

DROP VIEW IF EXISTS joined_set;
CREATE VIEW joined_set (set_id, set_name, set_code, set_type, nonfoil_only, foil_only ,card_count, released_at, digital, parent_set)
    AS
    SELECT s.set_id, s.set_name, s.set_code, stl.set_type, s.nonfoil_only, s.foil_only, COUNT(cv.set_id) AS card_count,s.released_at, s.digital, ss.set_name 
    FROM sets s
    LEFT JOIN sets ss ON s.parent_set = ss.set_id
    JOIN set_type_list_ref stl ON s.set_type_id = stl.set_type_id
    JOIN card_version cv ON cv.set_id = s.set_id
    GROUP BY s.set_id,  stl.set_type, s.released_at,  ss.set_id;

CREATE  MATERIALIZED VIEW IF NOT EXISTS joined_set_materialized (set_id, set_name, set_code, set_type, card_count, released_at, digital)
    AS
    SELECT s.set_id, s.set_name, s.set_code, stl.set_type,  COUNT(cv.set_id) AS card_count,s.released_at, s.digital
    FROM sets s
    JOIN set_type_list_ref stl ON s.set_type_id = stl.set_type_id
    JOIN card_version cv ON cv.set_id = s.set_id
    GROUP BY s.set_id,  stl.set_type, s.released_at;

-- Speeds up JOIN between sets and set_type_list_ref
CREATE INDEX idx_sets_set_type_id ON sets(set_type_id);

-- Speeds up JOIN between card_version and sets
CREATE INDEX idx_card_version_set_id ON card_version(set_id);

CREATE INDEX ON joined_set_materialized(set_code); 

--function to insert a new set
CREATE OR REPLACE FUNCTION insert_joined_set(
    p_set_id UUID,
    p_set_name TEXT,
    p_set_code TEXT,
    p_set_type TEXT,
    p_released_at DATE,
    p_digital BOOLEAN,
    p_nonfoil_only BOOLEAN,
    p_foil_only BOOLEAN,
    p_parent_set UUID,
    p_uri TEXT
)
RETURNS VOID AS $$
DECLARE
    v_set_type_id INT;
    v_parent_id UUID;
    v_icon_query_id INT;
BEGIN
    -- Upsert set type
    INSERT INTO set_type_list_ref (set_type)
    VALUES (p_set_type)
    ON CONFLICT (set_type) DO NOTHING;

    SELECT set_type_id INTO v_set_type_id
    FROM set_type_list_ref
    WHERE set_type = p_set_type;

    RAISE NOTICE 'Set type: %, ID: %', p_set_type, v_set_type_id;

    -- Optional: Get parent set ID
    SELECT set_id INTO v_parent_id
    FROM sets
    WHERE set_code = p_parent_set;

    -- Insert set
    INSERT INTO sets (
        set_id, set_name, set_code, set_type_id, released_at,
        digital, nonfoil_only, foil_only, parent_set
    )
    VALUES (
        p_set_id, p_set_name, p_set_code, v_set_type_id,
        p_released_at, p_digital, p_nonfoil_only, p_foil_only, v_parent_id
    )
    ON CONFLICT (set_id) DO NOTHING;

    IF NOT EXISTS (SELECT 1 FROM sets WHERE set_id = p_set_id) THEN
        RAISE NOTICE 'Set not inserted (conflict or error).';
    ELSE
        RAISE NOTICE 'Set inserted successfully.';
    END IF;

    -- add the icon uri
    INSERT INTO icon_query_ref (icon_query_uri)
    VALUES (p_uri)
    ON CONFLICT (icon_query_uri) DO NOTHING;

    -- Get icon_query_id
    SELECT icon_query_id INTO v_icon_query_id
    FROM icon_query_ref
    WHERE icon_query_uri = p_uri;

    RAISE NOTICE 'Icon URI: %, ID: %', p_uri, v_icon_query_id;

    -- 5. Link icon to set
    IF v_icon_query_id IS NOT NULL THEN
        INSERT INTO icon_set (icon_query_id, set_id)
        VALUES (v_icon_query_id, p_set_id)
        ON CONFLICT DO NOTHING;

        IF NOT EXISTS (
            SELECT 1 FROM icon_set WHERE icon_query_id = v_icon_query_id AND set_id = p_set_id
        ) THEN
            RAISE NOTICE 'Set-icon link not inserted (conflict or error).';
        ELSE
            RAISE NOTICE 'Set-icon link inserted successfully.';
        END IF;
    ELSE
        RAISE NOTICE 'Icon ID could not be resolved. Skipping set-icon link.';
    END IF;
END;
$$ LANGUAGE plpgsql;

--a trigger to insert a new set
CREATE OR REPLACE FUNCTION trigger_insert_on_joined_set()
RETURNS trigger AS $$
BEGIN
    PERFORM insert_joined_set(
        NEW.set_name,
        NEW.set_code,
        NEW.set_type,
        NEW.released_at,
        NEW.digital,
        NEW.nonfoil_only,
        NEW.foil_only,
        NEW.parent_set
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_insert_joined_set
INSTEAD OF INSERT ON joined_set
FOR EACH ROW EXECUTE FUNCTION trigger_insert_on_joined_set();