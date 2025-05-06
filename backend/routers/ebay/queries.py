

from backend.dependancies import get_settings, Settings

settings : Settings = get_settings()
encryption_key = settings.secret_key

nsert_token_query =  """INSERT INTO ebay_tokens (user_id, refresh_token, aquired_on, expires_on, token_type)
                        VALUES (%s, %s, %s, %s, %s);
                        """
get_info_login = f""" SELECT app_id, redirect_uri, response_type, pgp_sym_decrypt(client_secret_encrypted, '{encryption_key}') AS decrypted_secret
                     FROM ebay_app
                     WHERE user_id = %s AND app_id = %s """

get_scopes_app = """ SELECT s.scope_description 
                    FROM scopes s
                    JOIN scope_app sa ON sa.scope_id = s.scope_id 
                    WHERE sa.app_id = %s ; """

register_user_query = """ INSERT INTO user_ebay (unique_id, dev_id) VALUES (%s, %s) ON CONFLICT (dev_id) DO NOTHING ; """

register_app_query = """ INSERT INTO app_info (app_id, redirect_uri, response_type, hashed_secret, client_secret_encrypted) VALUES (%s, %s, %s, %s, pgp_sym_encrypt(%s, %s) ON CONFLICT (app_id) DO NOTHING; """

register_scope_query = "INSERT INTO scopes (scope_description) VALUES (%s) RETURNING scope_id; "
assign_user_app_query = """ INSERT INTO app_user (dev_id, app_id) VALUES (%s, %s) ON CONFLICT (dev_id, app_id) DO NOTHING; """
assign_refresh_token_query = """ INSERT INTO ebay_token (dev_id, app_id, refresh_token, expires_on, token_type ) VALUES (%s, %s, %s, %s, %s); """
assign_scope_query = """
                            INSERT INTO scope_app (scope_id, app_id)
                            SELECT scope_id, %s
                            FROM scopes
                            WHERE scope_description = %s
                            ON CONFLICT (scope_id, app_id) DO NOTHING; """


