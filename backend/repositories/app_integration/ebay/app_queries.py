get_scopes_app = """ SELECT s.scope_url
                    FROM scopes s
                    JOIN scope_app sa ON sa.scope_id = s.scope_id
                    WHERE sa.app_id = $1; """

register_app_query = """ 
INSERT INTO app_info (
    app_id,
    app_name,
    redirect_uri,
    response_type,
    client_secret_encrypted,
    environment,
    description
)
VALUES (
    $1, $2, $3, $4, pgp_sym_encrypt($5, $8), $6, $7
) 
ON CONFLICT (app_id) 
DO NOTHING
RETURNING app_id; """


register_app_scopes_query = """
INSERT INTO scope_app (scope_id, app_id)
SELECT s.scope_id, $1
FROM unnest($2::TEXT[]) AS scope_urls(scope_url)
JOIN scopes s ON s.scope_url = scope_urls.scope_url
ON CONFLICT (scope_id, app_id) DO NOTHING;
"""

assign_user_app_query = """ INSERT INTO app_user (dev_id, app_id) VALUES ($1, $2) ON CONFLICT (dev_id, app_id) DO NOTHING; """

assign_scope_query = """
                            INSERT INTO scope_app (scope_id, app_id)
                            SELECT scope_id, $1
                            FROM scopes
                            WHERE scope_url = $2
                            ON CONFLICT (scope_id, app_id) DO NOTHING; """
