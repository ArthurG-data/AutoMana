from backend.schemas.settings import EbaySettings, get_settings
from dotenv import load_dotenv
import os 
# Load environment variables explicitly
load_dotenv()

settings = EbaySettings(
    encrypt_algorithm=os.getenv("ENCRYPT_ALGORITHM", "HS256"),  # Use env var with default
    pgp_secret_key=os.getenv("PGP_SECRET_KEY")                  # Use env var
)

encryption_key = settings.pgp_secret_key

#eeds to be changed next to work with a user instread of app and dev
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
                                                      WHERE app_id = $1
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
                      
assign_ebay_token_query  =  """
                              WITH update_existing AS (
                                    -- Case 1: inserting a refresh_token → mark all refresh_token as used
                                    -- Case 2: inserting an access_token → mark only the most recent access_token as used
                                    UPDATE ebay_tokens
                                    SET used = true
                                    WHERE token_id IN (
                                          SELECT token_id
                                          FROM ebay_tokens
                                          WHERE app_id = $1 AND token_type = $2 AND used = false
                                          ORDER BY 
                                                CASE 
                                                WHEN $2 = 'refresh_token' THEN acquired_on -- for refresh_token → all match
                                                ELSE acquired_on DESC                     -- for access_token → top 1
                                                END
                                          LIMIT CASE WHEN $2 = 'refresh_token' THEN NULL ELSE 1 END
                                    )
                                    )
                                    INSERT INTO ebay_tokens (dev_id, app_id, token, acquired_on, expires_on, token_type, used)
                                    SELECT 
                                    ue.dev_id, 
                                    $1,                -- app_id
                                    $2,                -- token (refresh or access token)
                                    $3,                -- acquired_on
                                    $4,                -- expires_on
                                    $5,                -- token_type
                                    false              -- used = false (new token is active)
                                    FROM user_ebay ue
                                    WHERE ue.unique_id = $6
                                    RETURNING token_id;
                        """

get_refresh_token_query = """ SELECT et.refresh_token
                              FROM ebay_tokens et
                              JOIN user_ebay ue ON ue.dev_id = et.dev_id
                              WHERE ue.unique_id = $1 AND et.app_id = $2;
                        """

get_info = f"""SELECT app_id, redirect_uri, response_type, pgp_sym_decrypt(client_secret_encrypted, '{encryption_key}') AS decrypted_secret """
get_info_login =    get_info + """FROM ebay_app
                     WHERE user_id = $1 AND app_id = $2 """

register_oauth_request = """
                              INSERT INTO log_oauth_request (unique_id, session_id,  request,app_id ) VALUES ($1,$2, $3, $4) RETURNING session_id;
"""
get_valid_oauth_request = """
                  SELECT session_id, app_id FROM  log_oauth_request
                  WHERE unique_id = $1 AND expires_on > now();
                  """