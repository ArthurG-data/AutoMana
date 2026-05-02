import logging

logger = logging.getLogger(__name__)


def get_info_login_query() -> str:
    """App settings query — key passed as bound parameter $3, never interpolated."""
    return """
        SELECT ai.app_id,
               ai.redirect_uri,
               ai.ru_name,
               ai.response_type,
               pgp_sym_decrypt(ai.client_secret_encrypted::bytea, $3) AS decrypted_secret,
               ai.environment
          FROM app_integration.app_info ai
          JOIN app_integration.app_user au ON au.app_id = ai.app_id
         WHERE au.user_id = $1 AND ai.app_code = $2
    """


# ---------------------------------------------------------------------------
# Refresh-token storage ($4 = pgp key, always a bound parameter)
# ---------------------------------------------------------------------------

# $1 user_id  $2 app_id  $3 refresh_token (plaintext)  $4 pgp_key  $5 expires_at  $6 key_version
UPSERT_REFRESH_TOKEN_QUERY = """
    INSERT INTO app_integration.ebay_refresh_tokens
        (user_id, app_id, refresh_token_encrypted, expires_at, key_version)
    VALUES (
        $1, $2,
        pgp_sym_encrypt($3, $4,
            'cipher-algo=aes256, s2k-mode=3, s2k-digest-algo=sha512, s2k-count=65011712'),
        $5, $6
    )
    ON CONFLICT (user_id, app_id) DO UPDATE SET
        refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
        expires_at              = EXCLUDED.expires_at,
        rotated_at              = now(),
        key_version             = EXCLUDED.key_version
    RETURNING user_id, app_id, issued_at, rotated_at;
"""

# FOR UPDATE serialises concurrent refresh attempts on the same (user_id, app_id).
# Full serialisation requires the caller to hold an explicit transaction.
# $1 user_id  $2 app_code  $3 pgp_key
FETCH_REFRESH_TOKEN_QUERY = """
    SELECT pgp_sym_decrypt(t.refresh_token_encrypted, $3) AS refresh_token,
           t.expires_at,
           t.key_version
      FROM app_integration.ebay_refresh_tokens t
      JOIN app_integration.app_info ai ON ai.app_id = t.app_id
     WHERE t.user_id = $1 AND ai.app_code = $2
       FOR UPDATE;
"""


# ---------------------------------------------------------------------------
# OAuth request log
# ---------------------------------------------------------------------------

register_oauth_request = """
    INSERT INTO app_integration.log_oauth_request (user_id, app_id, status)
    VALUES ($1, $2, $3)
    RETURNING unique_id;
"""

get_valid_oauth_request = """
    SELECT ai.app_id, lor.user_id, ai.app_code
      FROM app_integration.log_oauth_request lor
      JOIN app_integration.app_info ai ON ai.app_id = lor.app_id
     WHERE lor.unique_id = $1 AND lor.expires_on > now();
"""

get_latest_pending_oauth_request = """
    SELECT lor.unique_id, ai.app_id, lor.user_id, ai.app_code
      FROM app_integration.log_oauth_request lor
      JOIN app_integration.app_info ai ON ai.app_id = lor.app_id
     WHERE lor.status = 'pending'
     ORDER BY lor.timestamp DESC
     LIMIT 1;
"""

complete_oauth_request_query = """
    UPDATE app_integration.log_oauth_request
       SET status = $2
     WHERE unique_id = $1 AND status = 'pending'
    RETURNING unique_id;
"""


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

get_app_scopes_query = """
    SELECT s.scope_url
      FROM app_integration.scope_app sa
      JOIN app_integration.scopes s ON sa.scope_id = s.scope_id
     WHERE sa.app_id = $1;
"""

# Returns user-specific scopes for (user_id, app_id). Empty result means fall
# back to app-level scopes. PK bug on scopes_user (missing app_id) is a known
# issue; it does not affect single-app testing.
get_user_scopes_query = """
    SELECT s.scope_url
      FROM app_integration.scopes_user su
      JOIN app_integration.scopes s ON su.scope_id = s.scope_id
     WHERE su.user_id = $1 AND su.app_id = $2;
"""
