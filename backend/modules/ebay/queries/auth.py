from backend.dependancies import get_general_settings, GeneralSettings

settings : GeneralSettings = get_general_settings()
encryption_key = settings.secret_key

assign_refresh_token_query = """ INSERT INTO ebay_token (dev_id, app_id, refresh_token, expires_on, token_type ) VALUES (%s, %s, %s, %s, %s); """

insert_token_query =  """INSERT INTO ebay_tokens (dev_id, app_id, refresh_token, acquired_on, expires_on, token_type)
                         SELECT ue.dev_id, %s, %s, %s, %s, %s
                         FROM user_ebay ue
                         WHERE ue.unique_id = %s
                         ON CONFLICT (dev_id, app_id) DO NOTHING;
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