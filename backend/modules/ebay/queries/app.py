get_scopes_app = """ SELECT s.scope_url
                    FROM scopes s
                    JOIN scope_app sa ON sa.scope_id = s.scope_id 
                    WHERE sa.app_id = %s ; """

register_app_query = """ INSERT INTO app_info (app_id, redirect_uri, response_type, hashed_secret, client_secret_encrypted) VALUES (%s, %s, %s, %s, pgp_sym_encrypt(%s, %s) ON CONFLICT (app_id) DO NOTHING; """
assign_user_app_query = """ INSERT INTO app_user (dev_id, app_id) VALUES (%s, %s) ON CONFLICT (dev_id, app_id) DO NOTHING; """
assign_scope_query = """
                            INSERT INTO scope_app (scope_id, app_id)
                            SELECT scope_id, %s
                            FROM scopes
                            WHERE scope_url = %s
                            ON CONFLICT (scope_id, app_id) DO NOTHING; """
