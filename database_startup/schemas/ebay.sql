CREATE TABLE IF NOT exists ebay_tokens(
    id SERIAL PRIMARY KEY,
    user_is UUID REFERENCES users(unique_id) ,
    refresh_token TEXT NOT NULL,
    acquired_on TIMESTAMP DEFAULT now(),
    expires_on TIMESTAMP NOT NULL,
    scopes TEXT[],
    token_type TEXT
)