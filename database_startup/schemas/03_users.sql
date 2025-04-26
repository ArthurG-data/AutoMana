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
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    device_id UUID UNIQUE, 
    active BOOLEAN DEFAULT TRUE
);


CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE NOT NULL,
    refresh_token TEXT NOT NULL,
    refresh_token_expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    revoked BOOLEAN DEFAULT FALSE
);

CREATE VIEW active_sessions_view AS
    SELECT u.username, s.created_at, s.expires_at AS session_expires_at, s.ip_address, s.user_agent, rt.refresh_token, rt.refresh_token_expires_at
    FROM sessions s
    JOIN refresh_tokens rt ON rt.session_id = s.id
    JOIN users u ON u.unique_id = s.user_id
    WHERE s.active = TRUE AND revoked = FALSE;


CREATE OR REPLACE FUNCTION insert_add_token(
    p_user_id UUID,
    p_created_at TIMESTAMPTZ,
    p_expires_at TIMESTAMPTZ,
    p_ip_address TEXT, 
    p_user_agent TEXT,
    p_refresh_token TEXT,
    p_refresh_token_expires_at TIMESTAMPTZ,
    p_device_id TEXT DEFAULT NULL
)
RETURNS TABLE (session_id UUID, token_id UUID) AS $$
DECLARE
    v_session_id UUID;
    v_refresh_token_id UUID;

BEGIN

    INSERT INTO sessions ( user_id, created_at, expires_at, ip_address, user_agent)
    VALUES (p_user_id, p_created_at, p_expires_at,p_ip_address, p_user_agent)

    RETURNING id INTO v_session_id;
  
    INSERT INTO refresh_tokens (
        session_id, refresh_token, refresh_token_expires_at
    )
    VALUES (
        v_session_id, p_refresh_token, p_refresh_token_expires_at
    )

    RETURNING refresh_tokens.token_id INTO v_refresh_token_id;

    RETURN SELECT v_session_id, v_refresh_token_id;
END;
$$ LANGUAGE plpgsql;

