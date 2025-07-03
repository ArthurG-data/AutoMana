CREATE EXTENSION IF NOT EXISTS pgcrypto;

--TABLES---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_ebay (
    unique_id UUID REFERENCES users(unique_id),
    dev_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
	updated_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);

CREATE TABLE IF NOT EXISTS app_info(
    --needs to be updated
    app_id TEXT PRIMARY KEY,
    redirect_uri VARCHAR(50) NOT NULL,
    response_type VARCHAR(20) NOT NULL,
    hashed_secret TEXT NOT NULL,
    client_secret_encrypted BYTEA NOT NULL;
    created_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS app_user (
    dev_id UUID REFERENCES user_ebay(dev_id) ON DELETE CASCADE NOT NULL,
    app_id TEXT REFERENCES app_info(app_id )  ON DELETE CASCADE NOT NULL,
    PRIMARY KEY (dev_id, app_id)
);


CREATE TABLE IF NOT EXISTS ebay_tokens(
    token_id SERIAL PRIMARY KEY,
    dev_id UUID REFERENCES user_ebay(dev_id) ON DELETE CASCADE NOT NULL,
    app_id TEXT REFERENCES app_info(app_id) ON DELETE CASCADE NOT NULL,
    token TEXT NOT NULL,
    acquired_on TIMESTAMPTZ DEFAULT now(),
    expires_on TIMESTAMPTZ NOT NULL,
    token_type TEXT,
    used BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS scopes (
    scope_id SERIAL PRIMARY KEY, 
    scope_url TEXT UNIQUE NOT NULL, 
    scope_description TEXT 
);

CREATE TABLE IF NOT EXISTS scope_app (
    scope_id INT REFERENCES scopes(scope_id) ON DELETE CASCADE, 
    app_id TEXT REFERENCES app_info(app_id), 
    granted_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (scope_id, app_id)
);


CREATE TABLE IF NOT EXISTS log_oauth_request (
    unique_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    timestamp TIMESTAMPTZ DEFAULT now(),
    expires_on TIMESTAMPTZ DEFAULT now() + INTERVAL '1 minute',
    request TEXT NOT NULL,
    app_id TEXT REFERENCES app_info(app_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_oauth_session ON log_oauth_request(session_id);

-- VEWS----------------------------------------------------------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW ebay_app AS 
    SELECT ai.app_id, ai.redirect_uri, ai.response_type,ai.client_secret_encrypted, ue.unique_id AS user_id
    FROM app_info ai
    JOIN app_user au  ON au.app_id = ai.app_id
    JOIN user_ebay ue on ue.dev_id = au.dev_id
--FUNCTIONS----------------------------------------------------------------------------------------------------------------------------------------------
