CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    username TEXT NOT NULL UNIQUE,
    unique_id UUID NOT NULL PRIMARY KEY DEFAULT uuid_generate_v4(),
	email VARCHAR(50) NOT NULL UNIQUE,
    fullname VARCHAR(50),
    hashed_password TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    disabled BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT now(),
    expires_at TIMESTAMP NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    active BOOLEAN DEFAULT TRUE
)