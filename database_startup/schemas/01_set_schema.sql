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
    parent_set UUID DEFAULT NULL,
    is_active BOOL DEFAULT TRUE,
    created_at DATE DEFAULT NOW(),
    updated_at DATE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS icon_query_ref(
    icon_query_id SERIAL PRIMARY KEY,
    icon_query_uri VARCHAR(500) UNIQUE NOT NULL
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
    WHERE s.is_active = TRUE
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

-- ✅ CREATE: Bulk set insert function that accepts JSON
CREATE OR REPLACE FUNCTION insert_batch_sets(sets_json JSONB)
RETURNS TABLE(
    total_sets INTEGER,
    successful_inserts INTEGER,
    failed_inserts INTEGER,
    success_rate NUMERIC(5,2),
    inserted_set_ids UUID[],
    errors TEXT[]
) AS $$
DECLARE
    set_record JSONB;
    v_set_id UUID;
    v_set_type_id INT;
    v_parent_id UUID;
    v_icon_query_id INT;
    v_total_sets INTEGER := 0;
    v_successful_inserts INTEGER := 0;
    v_failed_inserts INTEGER := 0;
    v_inserted_set_ids UUID[] := ARRAY[]::UUID[];
    v_errors TEXT[] := ARRAY[]::TEXT[];
    v_error_msg TEXT;
BEGIN
    -- Count total sets in JSON
    SELECT jsonb_array_length(sets_json) INTO v_total_sets;
    
    -- Log start of processing
    RAISE NOTICE 'Starting bulk set insert for % sets', v_total_sets;
    
    -- Loop through each set in the JSON array
    FOR set_record IN SELECT jsonb_array_elements(sets_json)
    LOOP
        BEGIN
            -- Extract set_id or generate new one
            v_set_id := COALESCE(
                (set_record->>'id')::UUID,
                (set_record->>'set_id')::UUID,
                uuid_generate_v4()
            );
            
            -- ✅ UPSERT: Set type
            INSERT INTO set_type_list_ref (set_type)
            VALUES (set_record->>'set_type')
            ON CONFLICT (set_type) DO NOTHING;
            
            -- Get set type ID
            SELECT set_type_id INTO v_set_type_id
            FROM set_type_list_ref
            WHERE set_type = set_record->>'set_type';
            
            -- ✅ HANDLE: Parent set (optional)
            v_parent_id := NULL;
            IF set_record ? 'parent_set_code' AND set_record->>'parent_set_code' IS NOT NULL THEN
                SELECT set_id INTO v_parent_id
                FROM sets
                WHERE set_code = set_record->>'parent_set_code';
            END IF;
            
            -- ✅ INSERT: Main set record
            INSERT INTO sets (
                set_id,
                set_name,
                set_code,
                set_type_id,
                released_at,
                digital,
                nonfoil_only,
                foil_only,
                parent_set
            )
            VALUES (
                v_set_id,
                set_record->>'name',
                set_record->>'code',
                v_set_type_id,
                (set_record->>'released_at')::DATE,
                COALESCE((set_record->>'digital')::BOOLEAN, FALSE),
                COALESCE((set_record->>'nonfoil_only')::BOOLEAN, FALSE),
                COALESCE((set_record->>'foil_only')::BOOLEAN, FALSE),
                v_parent_id
            )
            ON CONFLICT (set_id) DO UPDATE SET
                set_name = EXCLUDED.set_name,
                set_code = EXCLUDED.set_code,
                set_type_id = EXCLUDED.set_type_id,
                released_at = EXCLUDED.released_at,
                digital = EXCLUDED.digital,
                nonfoil_only = EXCLUDED.nonfoil_only,
                foil_only = EXCLUDED.foil_only,
                parent_set = EXCLUDED.parent_set,
                updated_at = NOW();
            
            -- ✅ HANDLE: Icon URI (if provided)
            IF set_record ? 'icon_svg_uri' AND set_record->>'icon_svg_uri' IS NOT NULL THEN
                -- Insert icon query reference
                INSERT INTO icon_query_ref (icon_query_uri)
                VALUES (set_record->>'icon_svg_uri')
                ON CONFLICT (icon_query_uri) DO NOTHING;
                
                -- Get icon query ID
                SELECT icon_query_id INTO v_icon_query_id
                FROM icon_query_ref
                WHERE icon_query_uri = set_record->>'icon_svg_uri';
                
                -- Link icon to set
                IF v_icon_query_id IS NOT NULL THEN
                    INSERT INTO icon_set (icon_query_id, set_id)
                    VALUES (v_icon_query_id, v_set_id)
                    ON CONFLICT DO NOTHING;
                END IF;
            END IF;
            
            -- ✅ SUCCESS: Increment counters
            v_successful_inserts := v_successful_inserts + 1;
            v_inserted_set_ids := array_append(v_inserted_set_ids, v_set_id);
            
        EXCEPTION WHEN OTHERS THEN
            -- ✅ ERROR HANDLING: Log error and continue
            v_failed_inserts := v_failed_inserts + 1;
            v_error_msg := format('Set %s failed: %s', 
                COALESCE(set_record->>'name', set_record->>'code', 'unknown'), 
                SQLERRM
            );
            v_errors := array_append(v_errors, v_error_msg);
            
            RAISE NOTICE 'Error inserting set: %', v_error_msg;
        END;
    END LOOP;
    
    -- ✅ REFRESH: Materialized view
    BEGIN
        REFRESH MATERIALIZED VIEW joined_set_materialized;
        RAISE NOTICE 'Refreshed materialized view joined_set_materialized';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Failed to refresh materialized view: %', SQLERRM;
    END;
    
    -- ✅ RETURN: Processing statistics
    RETURN QUERY SELECT 
        v_total_sets,
        v_successful_inserts,
        v_failed_inserts,
        CASE 
            WHEN v_total_sets > 0 THEN ROUND((v_successful_inserts::NUMERIC / v_total_sets::NUMERIC) * 100, 2)
            ELSE 0.00
        END,
        v_inserted_set_ids,
        v_errors;
    
    RAISE NOTICE 'Bulk set insert completed: %/% successful', v_successful_inserts, v_total_sets;
END;
$$ LANGUAGE plpgsql;

-- ✅ HELPER: Function to process large JSON files (similar to cards)
CREATE OR REPLACE FUNCTION process_large_sets_json(
    file_path TEXT,
    batch_size INTEGER DEFAULT 100
)
RETURNS TABLE(
    total_sets INTEGER,
    successful_inserts INTEGER,
    failed_inserts INTEGER,
    success_rate NUMERIC(5,2),
    batches_processed INTEGER,
    processing_time_seconds NUMERIC,
    inserted_set_ids UUID[],
    errors TEXT[]
) AS $$
DECLARE
    sets_json JSONB;
    batch_json JSONB;
    batch_result RECORD;
    v_total_sets INTEGER := 0;
    v_successful_inserts INTEGER := 0;
    v_failed_inserts INTEGER := 0;
    v_batches_processed INTEGER := 0;
    v_all_inserted_ids UUID[] := ARRAY[]::UUID[];
    v_all_errors TEXT[] := ARRAY[]::TEXT[];
    v_start_time TIMESTAMP;
    v_end_time TIMESTAMP;
    v_processing_time NUMERIC;
    i INTEGER;
BEGIN
    v_start_time := clock_timestamp();
    
    -- ✅ LOAD: JSON file content
    BEGIN
        SELECT pg_read_file(file_path)::JSONB INTO sets_json;
        RAISE NOTICE 'Loaded JSON file: %', file_path;
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'Failed to load JSON file %: %', file_path, SQLERRM;
    END;
    
    -- Validate JSON structure
    IF jsonb_typeof(sets_json) != 'array' THEN
        RAISE EXCEPTION 'JSON file must contain an array of sets';
    END IF;
    
    v_total_sets := jsonb_array_length(sets_json);
    RAISE NOTICE 'Processing % sets in batches of %', v_total_sets, batch_size;
    
    -- ✅ PROCESS: In batches
    FOR i IN 0..v_total_sets-1 BY batch_size
    LOOP
        -- Extract batch
        SELECT jsonb_agg(elem) INTO batch_json
        FROM (
            SELECT jsonb_array_elements(sets_json) AS elem
            LIMIT batch_size OFFSET i
        ) sub;
        
        v_batches_processed := v_batches_processed + 1;
        RAISE NOTICE 'Processing batch % with % sets', v_batches_processed, jsonb_array_length(batch_json);
        
        -- Process batch
        SELECT * INTO batch_result
        FROM insert_batch_sets(batch_json);
        
        -- Accumulate results
        v_successful_inserts := v_successful_inserts + batch_result.successful_inserts;
        v_failed_inserts := v_failed_inserts + batch_result.failed_inserts;
        v_all_inserted_ids := v_all_inserted_ids || batch_result.inserted_set_ids;
        v_all_errors := v_all_errors || batch_result.errors;
        
        RAISE NOTICE 'Batch % completed: %/% successful', 
            v_batches_processed, batch_result.successful_inserts, batch_result.total_sets;
    END LOOP;
    
    v_end_time := clock_timestamp();
    v_processing_time := EXTRACT(EPOCH FROM v_end_time - v_start_time);
    
    -- ✅ RETURN: Final statistics
    RETURN QUERY SELECT 
        v_total_sets,
        v_successful_inserts,
        v_failed_inserts,
        CASE 
            WHEN v_total_sets > 0 THEN ROUND((v_successful_inserts::NUMERIC / v_total_sets::NUMERIC) * 100, 2)
            ELSE 0.00
        END,
        v_batches_processed,
        v_processing_time,
        v_all_inserted_ids,
        v_all_errors;
    
    RAISE NOTICE 'Large sets JSON processing completed in % seconds: %/% sets successful', 
        v_processing_time, v_successful_inserts, v_total_sets;
END;
$$ LANGUAGE plpgsql;
