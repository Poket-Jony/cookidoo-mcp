-- OAuth 2.1 multi-tenant schema for the http transport.
-- Idempotent: safe to re-run on every startup.

CREATE TABLE IF NOT EXISTS cookidough_accounts (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    encrypted_password TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oauth_codes (
    code TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES cookidough_accounts (id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    redirect_uri_provided_explicitly BOOLEAN NOT NULL,
    code_challenge TEXT NOT NULL,
    scopes JSONB NOT NULL DEFAULT '[]',
    resource TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id TEXT PRIMARY KEY,
    access_token_hash TEXT UNIQUE NOT NULL,
    refresh_token_hash TEXT UNIQUE,
    client_id TEXT NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES cookidough_accounts (id) ON DELETE CASCADE,
    scopes JSONB NOT NULL DEFAULT '[]',
    resource TEXT,
    access_token_expires_at TIMESTAMPTZ NOT NULL,
    refresh_token_expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_oauth_codes_expires_at ON oauth_codes (expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_access_expires_at ON oauth_tokens (access_token_expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_refresh_expires_at ON oauth_tokens (refresh_token_expires_at);
