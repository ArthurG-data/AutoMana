import logging
from backend.core.settings import Settings, get_settings as get_general_settings
from dotenv import load_dotenv
import os 
logger = logging.getLogger(__name__)
# Load environment variables explicitly
load_dotenv()

def get_encryption_key() -> str:
    """Get encryption key dynamically"""
    logger.info("Fetching encryption key from settings")
    try:
        settings = get_settings()
        key = settings.pgp_secret_key
        
        if not key or key == 'fallback-key-change-in-production':
            logger.warning("Using default encryption key! Set PGP_SECRET_KEY environment variable!")
        
        return key
    except Exception as e:
        logger.error(f"Failed to get encryption key: {e}")
        return 'fallback-key-change-in-production'

def get_info_login_query() -> str:
    """Build info query with current encryption key"""
    return f"""SELECT 
                ai.app_id, 
                ai.redirect_uri, 
                ai.response_type,
                pgp_sym_decrypt(ai.client_secret_encrypted::bytea, $3) AS decrypted_secret,
                ai.environment
            FROM app_info ai
            JOIN app_user au ON au.app_id = ai.app_id
            WHERE au.user_id = $1 AND ai.app_code = $2
            """

#needs to be changed next to work with a user instread of app and dev
assign_access_ebay_query ="""
                        WITH update_existing AS (
                                                      UPDATE ebay_tokens
                                                      SET used = true
                                                      WHERE app_id = $1 AND token_type = 'access_token'
                                                      )
                                                      INSERT INTO ebay_tokens (dev_id, app_id, token, acquired_on, expires_on, token_type, used)
                                                      SELECT 
                                                      ue.dev_id, 
                                                      $1,               -- app_id
                                                      $2,               -- refresh_token
                                                      $3,               -- acquired_on
                                                      $4,               -- expires_on
                                                      $5,  -- token_type
                                                      false             -- used
                                                      FROM user_ebay ue
                                                      WHERE ue.unique_id = $6
                                                      RETURNING token_id;
                                                """
assign_refresh_ebay_query ="""
                                                WITH update_existing AS (
                            UPDATE ebay_tokens
                            SET used = true
                            WHERE app_id = $1 AND token_type = 'refresh_token' AND used = false
                        )
                        INSERT INTO ebay_tokens (app_id, token, acquired_on, expires_on, token_type, used)
                        VALUES ()
                            $1,               -- app_id
                            $2,               -- refresh_token
                            $3,               -- acquired_on
                            $4,               -- expires_on
                            $5,               -- token_type ('refresh_token')
                            false             -- used
                            )
                        RETURNING token_id;
                                                """
                      
assign_ebay_token_query  =  """
                            WITH update_existing AS (
                                UPDATE ebay_tokens
                                SET used = true
                                WHERE app_id = $1 
                                AND token_type = $5 
                                AND used = false
                                AND (
                                    -- For refresh tokens: mark all as used
                                    ($5 = 'refresh_token') 
                                    OR 
                                    -- For access tokens: mark only the most recent as used
                                    ($5 = 'access_token' AND token_id = (
                                        SELECT token_id 
                                        FROM ebay_tokens 
                                        WHERE app_id = $1 AND token_type = 'access_token' AND used = false
                                        ORDER BY acquired_on DESC 
                                        LIMIT 1
                                    ))
                                )
                            )
                            INSERT INTO ebay_tokens (app_id, token, acquired_on, expires_on, token_type, used)
                            VALUES (
                                $1,     -- app_id
                                $2,     -- token (refresh or access token)
                                $3,     -- acquired_on
                                $4,     -- expires_on
                                $5,     -- token_type
                                false   -- used = false (new token is active)
                            )
                            RETURNING token_id;
                        """

get_refresh_token_query = """ SELECT et.refresh_token
                              FROM ebay_tokens et
                              JOIN user_ebay ue ON ue.dev_id = et.dev_id
                              WHERE ue.unique_id = $1 AND et.app_id = $2;
                        """

get_info = f"""SELECT ai.app_id, ai.redirect_uri, ai.response_type, pgp_sym_decrypt(client_secret_encrypted, '{get_general_settings().pgp_secret_key}') AS decrypted_secret """
get_info_login =    get_info + """FROM app_info ai
                              JOIN app_user au ON au.app_id = ai.app_id
                     WHERE au.user_id = $1 AND ai.app_id = $2 """

register_oauth_request = """
                              INSERT INTO log_oauth_request 
                                    (
                                     user_id
                                    ,app_id
                                    ,status) 
                              VALUES ($1,$2, $3) 
                              RETURNING unique_id;
"""
get_valid_oauth_request = """
                  SELECT ai.app_id , lor.user_id, ai.app_code
                  FROM  log_oauth_request lor
                  JOIN app_info ai ON ai.app_id = lor.app_id
                  WHERE lor.unique_id = $1 AND  expires_on > now();
                  """
complete_oauth_request_query = """
UPDATE log_oauth_request 
SET 
    status = $2,
    completed_at = now(),
    updated_at = now()
WHERE state_token = $1 AND status = 'pending'
RETURNING unique_id;
"""

get_app_scopes_query = """
SELECT s.scope_url
FROM scope_app sa
JOIN scopes s ON sa.scope_id = s.scope_id
WHERE sa.app_id = $1;
"""

detect_suspicious_oauth_activity_query = """
SELECT 
    user_id, COUNT(*) as attempt_count,
    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_count
FROM log_oauth_request
WHERE timestamp > now() - INTERVAL '1 hour'
    AND user_id = $1
GROUP BY user_id
HAVING COUNT(*) > 10 OR COUNT(CASE WHEN status = 'failed' THEN 1 END) > 5;
"""