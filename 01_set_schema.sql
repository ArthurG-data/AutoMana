CREATE TABLE IF NOT EXISTS set_type_list_ref(
    set_type_id SERIAL NOT NULL PRIMARY KEY,
    set_type VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS foil_status_ref(
    foil_status_id INT NOT NULL PRIMARY KEY,
    foil_status_desc VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS icon_query_ref(
    icon_query_id INT NOT NULL PRIMARY KEY, 
    icon_quey TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sets(
    set_id UUID NOT NULL PRIMARY KEY,
    set_name VARCHAR(100) UNIQUE NOT NULL,
    set_code VARCHAR(10) UNIQUE NOT NULL,
    set_type_id INT NOT NULL REFERENCES set_type_list_ref(set_type_id),
    released_at DATE NOT NULL,
    digital BOOL DEFAULT FALSE,
    foil_status_id INT NOT NULL REFERENCES foil_status_ref(foil_status_id),
    parent_set UUID DEFAULT NULL,
    icon_query_id INT REFERENCES icon_query_ref(icon_query_id)
);




