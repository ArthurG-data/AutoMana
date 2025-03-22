DROP TABLE users;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    username TEXT NOT NULL UNIQUE,
    unique_id UUID NOT NULL PRIMARY KEY DEFAULT uuid_generate_v4(),
	email VARCHAR(50) NOT NULL UNIQUE,
    fullname VARCHAR(50),
    hashed_password TEXT,
    disabled BOOLEAN DEFAULT FALSE
);