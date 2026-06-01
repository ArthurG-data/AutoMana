-- migration_43: add password_reset_tokens table for forgot-password flow
CREATE TABLE IF NOT EXISTS user_management.password_reset_tokens (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES user_management.users(unique_id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL UNIQUE,
    expires_at    TIMESTAMPTZ NOT NULL,
    used_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prt_user_id ON user_management.password_reset_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_prt_expires_at ON user_management.password_reset_tokens (expires_at);
