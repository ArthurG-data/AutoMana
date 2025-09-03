CREATE EXTENSION IF NOT EXISTS pgcrypto;

--TABLES---------------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS app_info(
    --needs to be updated, maybe add cient id??
    app_id TEXT PRIMARY KEY,
    app_name VARCHAR(100) NOT NULL,
    redirect_uri VARCHAR(50) NOT NULL,
    response_type VARCHAR(20) NOT NULL,
    client_secret_encrypted TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'SANDBOX',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE,
    app_code VARCHAR(50) UNIQUE NOT NULL,
    UNIQUE (app_id, environment)
);


CREATE TABLE IF NOT EXISTS app_user (
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE NOT NULL,
    app_id TEXT REFERENCES app_info(app_id )  ON DELETE CASCADE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (user_id, app_id)
);

CREATE TABLE IF NOT EXISTS ebay_tokens(
    token_id SERIAL PRIMARY KEY,
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
--new implementation -> allowed to an app, and then user with a subset of that
CREATE TABLE IF NOT EXISTS scope_app (
    scope_id INT REFERENCES scopes(scope_id) ON DELETE CASCADE, 
    app_id TEXT REFERENCES app_info(app_id), 
    granted_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (scope_id, app_id)
);

CREATE TABLE IF NOT EXISTS scopes_user(
    scope_id INT REFERENCES scopes(scope_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE,
    app_id TEXT REFERENCES app_info(app_id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (scope_id, user_id)
);

CREATE TABLE IF NOT EXISTS log_oauth_request (
    unique_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE,
    app_id TEXT REFERENCES app_info(app_id) ON DELETE CASCADE,
    request TEXT,
    timestamp TIMESTAMPTZ DEFAULT now(),
    expires_on TIMESTAMPTZ DEFAULT now() + INTERVAL '1 minute',
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oauth_session ON log_oauth_request(session_id);

-- VEWS----------------------------------------------------------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW ebay_app AS 
    SELECT ai.app_id, ai.redirect_uri, ai.response_type,ai.client_secret_encrypted, ue.unique_id AS user_id
    FROM app_info ai
    JOIN app_user au  ON au.app_id = ai.app_id
    JOIN user_ebay ue on ue.dev_id = au.dev_id
--FUNCTIONS----------------------------------------------------------------------------------------------------------------------------------------------
