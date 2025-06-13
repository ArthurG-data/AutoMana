from backend.dependancies import get_ebay_settings, EbaySettings

settings : EbaySettings = get_ebay_settings()
encryption_key = settings.pgp_secret_key

#eeds to be changed next to work with a user instread of app and dev
assign_access_ebay_query ="""
                        WITH update_existing AS (
                                                      UPDATE ebay_tokens
                                                      SET used = true
                                                      WHERE app_id = %s AND token_type = 'access_token'
                                                      )
                                                      INSERT INTO ebay_tokens (dev_id, app_id, token, acquired_on, expires_on, token_type, used)
                                                      SELECT 
                                                      ue.dev_id, 
                                                      %s,               -- app_id
                                                      %s,               -- refresh_token
                                                      %s,               -- acquired_on
                                                      %s,               -- expires_on
                                                      %s,  -- token_type
                                                      false             -- used
                                                      FROM user_ebay ue
                                                      WHERE ue.unique_id = %s
                                                      RETURNING token_id;
                                                """
assign_refresh_ebay_query ="""
                        WITH update_existing AS (
                                                      UPDATE ebay_tokens
                                                      SET used = true
                                                      WHERE app_id = %s
                                                      )
                                                      INSERT INTO ebay_tokens (dev_id, app_id, token, acquired_on, expires_on, token_type, used)
                                                      SELECT 
                                                      ue.dev_id, 
                                                      %s,               -- app_id
                                                      %s,               -- refresh_token
                                                      %s,               -- acquired_on
                                                      %s,               -- expires_on
                                                      %s,  -- token_type
                                                      false             -- used
                                                      FROM user_ebay ue
                                                      WHERE ue.unique_id = %s
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
                                          WHERE app_id = %s AND token_type = %s AND used = false
                                          ORDER BY 
                                                CASE 
                                                WHEN %s = 'refresh_token' THEN acquired_on -- for refresh_token → all match
                                                ELSE acquired_on DESC                     -- for access_token → top 1
                                                END
                                          LIMIT CASE WHEN %s = 'refresh_token' THEN NULL ELSE 1 END
                                    )
                                    )
                                    INSERT INTO ebay_tokens (dev_id, app_id, token, acquired_on, expires_on, token_type, used)
                                    SELECT 
                                    ue.dev_id, 
                                    %s,                -- app_id
                                    %s,                -- token (refresh or access token)
                                    %s,                -- acquired_on
                                    %s,                -- expires_on
                                    %s,                -- token_type
                                    false              -- used = false (new token is active)
                                    FROM user_ebay ue
                                    WHERE ue.unique_id = %s
                                    RETURNING token_id;
                        """

get_refresh_token_query = """ SELECT et.refresh_token
                              FROM ebay_tokens et
                              JOIN user_ebay ue ON ue.dev_id = et.dev_id
                              WHERE ue.unique_id = %s AND et.app_id = %s;
                        """

get_info = f"""SELECT app_id, redirect_uri, response_type, pgp_sym_decrypt(client_secret_encrypted, '{encryption_key}') AS decrypted_secret """
get_info_login =    get_info + """FROM ebay_app
                     WHERE user_id = %s AND app_id = %s """

register_oauth_request = """
                              INSERT INTO log_oauth_request (unique_id, session_id,  request,app_id ) VALUES (%s,%s, %s, %s) RETURNING session_id;
"""
get_valid_oauth_request = """
                  SELECT session_id, app_id FROM  log_oauth_request
                  WHERE unique_id = %s AND expires_on > now();
                  """