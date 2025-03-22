CREATE TABLE IF NOT EXISTS set_type_list(
    set_type_id UUID NOT NULL PRIMARY KEY,
    set_type VARCHAR(20) UNIQUE DEFAULT(none)
);



CREATE TABLE IF NOT EXISTS sets(
    set_id UUID NOT NULL PRIMARY KEY,
    set_name VARCHAR(100) NOT NULL,
    set_code VARCHAR(10) UNIQUE NOT NULL,
    set_type_id UUID NOT NULL REFERENCES set_type_list(set_type_id),
    released_at DATE NOT NULL,
    digital BOOL DEFAULT FALSE,
    parent_set UUID DEFAULT NULL
);




CREATE TABLE IF NOT EXISTS set_url_source_list(
    source_id UUID NOT NULL,
    url_source VARCHAR(20) NOT NULL,
    PRIMARY KEY (source_id)
);

CREATE TABLE IF NOT EXISTS set_url(
    set_id UUID NOT NULL REFERENCES sets(set_id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES set_url_source_list(source_id) ON DELETE CASCADE, 
    uri TEXT NOT NULL,
    PRIMARY KEY (set_id, source_id) 
);
