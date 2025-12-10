CREATE SCHEMA sql_agent_metadata;

CREATE TABLE IF NOT EXISTS sql_agent_metadata.object_ref(
    id SERIAL PRIMARY KEY,
    object_type TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
INSERT INTO sql_agent_metadata.object_ref (object_type)
VALUES ('schema'), ('table'), ('column'), ('relationship');
--a table to store the entities used for metadata creation
CREATE TABLE sql_agent_metadata.entity (
    id BIGSERIAL PRIMARY KEY,
    entity_type_id INT NOT NULL REFERENCES sql_agent_metadata.object_ref(id),
    db_name TEXT NOT NULL,
    schema_name TEXT,
    object_name TEXT NOT NULL, -- table/column/relationship name
    parent_entity_id BIGINT REFERENCES sql_agent_metadata.entity(id), -- for hierarchy (column->table, table->schema)
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (entity_type_id, db_name, schema_name, object_name, parent_entity_id)
);

-- Attributes for entities (flexible key-value storage)
CREATE TABLE sql_agent_metadata.entity_attribute (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES sql_agent_metadata.entity(id) ON DELETE CASCADE,
    attribute_key TEXT NOT NULL, -- 'data_type', 'is_nullable', 'row_count', 'description', etc.
    attribute_value TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (entity_id, attribute_key)
);


------------------table for the vector database mappings----------------------
CREATE TABLE IF NOT EXISTS sql_agent_metadata.schema_embeddings (
    id BIGSERIAL PRIMARY KEY,
    object_id BIGINT REFERENCES sql_agent_metadata.entity(id),
    name TEXT NOT NULL, --the name of the column, table or relation 
    description TEXT,
    embedding vector(1536) NOT NULL, --for openAI
    embedding_model TEXT DEFAULT 'text-embedding-3-small', --default embedding model
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (object_id, embedding_model)
);

--add an index for similarity_search
CREATE INDEX schema_embeddings_ivfflat_idx
ON sql_agent_metadata.schema_embeddings
USING ivfflat (embedding vector_l2_ops)
WITH (lists = 100);
ANALYZE sql_agent_metadata.schema_embeddings;--analyse required fro performance

---------------------------------------------------
-- Function to insert raw metadata from JSONB inputs

CREATE OR REPLACE FUNCTION sql_agent_metadata.insert_raw_metadata(
    p_entities JSONB,
    p_attributes JSONB
) RETURNS VOID AS $$
BEGIN
    -- Create temp tables
    CREATE TEMP TABLE temp_entities ON COMMIT DROP AS
    SELECT * 
    FROM jsonb_to_recordset(p_entities) AS x (
        entity_type_name TEXT,
        db_name TEXT,
        schema_name TEXT,
        object_name TEXT,
        parent_entity_name TEXT
    );

    CREATE TEMP TABLE temp_attributes ON COMMIT DROP AS
    SELECT * 
    FROM jsonb_to_recordset(p_attributes) AS x (
        entity_name TEXT,
        attribute_key TEXT,
        attribute_value TEXT
    );

    -- Insert schemas (no parent)
    INSERT INTO sql_agent_metadata.entity (entity_type_id, db_name, schema_name, object_name, parent_entity_id)
    SELECT 
        o.id,
        te.db_name,
        te.schema_name,
        te.object_name,
        NULL
    FROM temp_entities te
    JOIN sql_agent_metadata.object_ref o ON o.object_type = te.entity_type_name
    WHERE te.entity_type_name = 'schema'
    ON CONFLICT (entity_type_id, db_name, schema_name, object_name, parent_entity_id)
    DO UPDATE SET updated_at = now();

    -- Insert tables (parent is schema)
    INSERT INTO sql_agent_metadata.entity (entity_type_id, db_name, schema_name, object_name, parent_entity_id)
    SELECT 
        o.id,
        te.db_name,
        te.schema_name,
        te.object_name,
        parent.id
    FROM temp_entities te
    JOIN sql_agent_metadata.object_ref o ON o.object_type = 'table'
    LEFT JOIN sql_agent_metadata.entity parent 
        ON parent.entity_type_id = (SELECT id FROM sql_agent_metadata.object_ref WHERE object_type = 'schema')
        AND parent.db_name = te.db_name
        AND parent.schema_name = te.schema_name
    WHERE te.entity_type_name = 'table'
    ON CONFLICT (entity_type_id, db_name, schema_name, object_name, parent_entity_id)
    DO UPDATE SET updated_at = now();

    -- Insert columns (parent is table)
    INSERT INTO sql_agent_metadata.entity (entity_type_id, db_name, schema_name, object_name, parent_entity_id)
    SELECT 
        o.id,
        te.db_name,
        te.schema_name,
        te.object_name,
        parent.id
    FROM temp_entities te
    JOIN sql_agent_metadata.object_ref o ON o.object_type = 'column'
    LEFT JOIN sql_agent_metadata.entity parent 
        ON parent.entity_type_id = (SELECT id FROM sql_agent_metadata.object_ref WHERE object_type = 'table')
        AND parent.db_name = te.db_name
        AND parent.schema_name = te.schema_name
        AND parent.object_name = te.parent_entity_name
    WHERE te.entity_type_name = 'column'
    ON CONFLICT (entity_type_id, db_name, schema_name, object_name, parent_entity_id)
    DO UPDATE SET updated_at = now();

    -- Insert attributes
    INSERT INTO sql_agent_metadata.entity_attribute (entity_id, attribute_key, attribute_value)
    SELECT 
        e.id,
        ta.attribute_key,
        ta.attribute_value
    FROM temp_attributes ta
    JOIN sql_agent_metadata.entity e 
        ON ta.entity_name = e.db_name || '.' || e.schema_name || 
           CASE 
               WHEN e.parent_entity_id IS NOT NULL THEN 
                   '.' || (SELECT object_name FROM sql_agent_metadata.entity WHERE id = e.parent_entity_id) || '.' || e.object_name
               ELSE 
                   '.' || e.object_name
           END
    ON CONFLICT (entity_id, attribute_key)
    DO UPDATE SET 
        attribute_value = EXCLUDED.attribute_value,
        updated_at = now();

END;
$$ LANGUAGE plpgsql;