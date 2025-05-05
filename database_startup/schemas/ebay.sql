--TABLES---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_ebay (
    unique_id UUID REFERENCES users(unique_id),
    dev_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
	updated_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);

CREATE TABLE IF NOT EXISTS app_info(
    app_id TEXT PRIMARY KEY,
    redirect_uri VARCHAR(50) NOT NULL,
    response_type VARCHAR(20) NOT NULL,
    hashed_secret TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS app_user (
    dev_id UUID REFERENCES user_ebay(dev_id) ON DELETE CASCADE NOT NULL,
    app_id TEXT REFERENCES app_info(app_id )  ON DELETE CASCADE NOT NULL,
    PRIMARY KEY (dev_id, app_id)
);



CREATE TABLE IF NOT EXISTS ebay_tokens(
    dev_id UUID REFERENCES user_ebay(dev_id) ON DELETE CASCADE NOT NULL,
    app_id TEXT REFERENCES app_info(app_id) ON DELETE CASCADE NOT NULL,
    refresh_token TEXT NOT NULL,
    acquired_on TIMESTAMPTZ DEFAULT now(),
    expires_on TIMESTAMPTZ NOT NULL,
    token_type TEXT,
    used BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (dev_id, app_id)
);

CREATE TABLE IF NOT EXISTS scopes (
    scope_id SERIAL PRIMARY KEY, 
    scope_description TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS scope_user (
    scope_id INT REFERENCES scopes(scope_id) ON DELETE CASCADE, 
    ebay_id UUID REFERENCES user_ebay(dev_id), 
    granted_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (scope_id, ebay_id)
);


--FUNCTIONS----------------------------------------------------------------------------------------------------------------------------------------------
