get_scopes_app = """ SELECT s.scope_url
                    FROM scopes s
                    JOIN scope_app sa ON sa.scope_id = s.scope_id
                    WHERE sa.app_id = $1; """

register_app_query = """ INSERT INTO app_info (app_id, redirect_uri, response_type, client_secret_encrypted) VALUES ($1, $2, $3, pgp_sym_encrypt($4, $5)) ON CONFLICT (app_id) DO NOTHING RETURNING 1; """
assign_user_app_query = """ INSERT INTO app_user (dev_id, app_id) VALUES ($1, $2) ON CONFLICT (dev_id, app_id) DO NOTHING; """
assign_scope_query = """
                            INSERT INTO scope_app (scope_id, app_id)
                            SELECT scope_id, $1
                            FROM scopes
                            WHERE scope_url = $2
                            ON CONFLICT (scope_id, app_id) DO NOTHING; """
