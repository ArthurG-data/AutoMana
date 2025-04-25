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
    device_id UUID UNIQUE, 
    active BOOLEAN DEFAULT TRUE
)


CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id SERIAL PRIMARY KEY,
    session_id INT REFERENCES sessions(id) ON DELETE CASCADE NOT NULL,
    refresh_token TEXT NOT NULL,
    refresh_token_expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    revoked BOOLEAN DEFAULT FALSE
)

CREATE VIEW active_sessions_view AS
    SELECT u.username, s.created_at, s.expires_at AS session_expires_at, s.ip_address, s.user_agent, rt.refresh_token, rt.refresh_token_expires_at
    FROM sessions s
    JOIN refresh_tokens rt ON rt.session_id = s.id
    JOIN users u ON u.unique_id = s.user_id
    WHERE s.active = TRUE AND revoked = FALSE;


CREATE OR REPLACE FUNCTION insert_add_token(
    p_user_id TEXT,
    p_created_at TIMESTAMP,
    p_expires_at TIMESTAMP,
    p_ip_address TEXT, 
    p_user_agent TEXT,
    p_refresh_token TEXT,
    p_refresh_token_expires_at TIMESTAMP,
    p_device_id TEXT
)
RETURNS INT AS $$
DECLARE
    v_session_id INT;
    v_token_id INT;
--fill
BEGIN
--create the session if none exists, if yes reset the time
    INSERT INTO sessions ( user_id, created_at, expires_at, ip_address, user_agent)
    VALUES (p_user_id, p_created_at, p_expires_at,p_ip_address, p_user_agent)
    RETURNING id INTO v_session_id;
    -- insert the token
    INSERT INTO refresh_token (
        session_id, refresh_token, refresh_token_expires_at
    )
    VALUES (
        v_session_id, p_refresh_token, p_refresh_token_expires_at
    )
    RETURNING id INTO v_token_id;

    RETURN v_token_id
END;
LANGUAGE LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION trigger_insert_add_add_token()
RETURNS trigger AS $$
BEGIN
    PERFORM insert_add_token(
        NEW.user_id,
        NEW.created_at,
        NEW.expires_at,
        NEW.ip_address,
        NEW.user_agent,
        NEW.refresh_token,
        NEW.refresh_token_expires_at
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER create_session
INSTEAD OF INSERT ON active_sessions_view
FOR EACH ROW 
EXECUTE FUNCTION trigger_insert_add_add_token();