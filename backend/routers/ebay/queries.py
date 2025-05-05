
insert_token_query =  """INSERT INTO ebay_tokens (user_id, refresh_token, aquired_on, expires_on, token_type)
                        VALUES (%s, %s, %s, %s, %s);
                        """

register_user_query = """ INSERT INTO user_ebay (unique_id, dev_id) VALUES (%s, %s) ON CONFLICT (dev_id) DO NOTHING ; """
register_app_query = """ INSERT INTO app_info (app_id, redirect_uri, response_type, hashed_secret) VALUES (%s, %s, %s, %s) ON CONFLICT app_id DO NOTHING; """
register_scope_query = "INSERT INTO scopes (scope_description) VALUES (%s) RETURNING scope_id; "
assign_user_app_query = """ INSERT INTO app_user (dev_id, app_id) VALUES (%s, %s) ON CONFLICT (dev_id, app_id) DO NOTHING; """
assign_refresh_token_query = """ INSERT INTO ebay_token (dev_id, app_id, refresh_token, expires_on, token_type ) VALUES (%s, %s, %s, %s, %s); """
assign_scope_query = """INSERT INTO scope_user (scope_id, ebay_id)
                        SELECT scope_id, %s
                        FROM scopes
                        WHERE scope_description = %s
                        ON CONFLICT (scope_id, ebay_id) DO NOTHING;"""


