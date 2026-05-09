get_scopes_app = """ SELECT s.scope_url
                    FROM scopes s
                    JOIN scope_app sa ON sa.scope_id = s.scope_id
                    WHERE sa.app_id = $1; """

register_app_query = """
INSERT INTO app_integration.app_info (
    app_id,
    app_name,
    redirect_uri,
    ru_name,
    response_type,
    client_secret_encrypted,
    environment,
    description,
    app_code
)
VALUES (
    $1, $2, $3, $3, $4, pgp_sym_encrypt($5, $9), $6, $7, $8
)
ON CONFLICT (app_id) DO UPDATE SET
    app_name                = EXCLUDED.app_name,
    redirect_uri            = EXCLUDED.redirect_uri,
    ru_name                 = EXCLUDED.ru_name,
    client_secret_encrypted = EXCLUDED.client_secret_encrypted,
    description             = EXCLUDED.description,
    updated_at              = now()
RETURNING app_code; """


register_app_scopes_query = """
INSERT INTO scope_app (scope_id, app_id)
SELECT s.scope_id, $1
FROM unnest($2::TEXT[]) AS scope_urls(scope_url)
JOIN scopes s ON s.scope_url = scope_urls.scope_url
ON CONFLICT (scope_id, app_id) DO NOTHING;
"""

assign_user_app_query = """ INSERT INTO app_integration.app_user (user_id, app_id) VALUES ($1, $2) ON CONFLICT (user_id, app_id) DO NOTHING; """

assign_user_scopes_query = """
INSERT INTO app_integration.scopes_user (scope_id, user_id, app_id)
SELECT s.scope_id, $1, $2
FROM unnest($3::TEXT[]) AS scope_urls(scope_url)
JOIN app_integration.scopes s ON s.scope_url = scope_urls.scope_url
ON CONFLICT (user_id, app_id, scope_id) DO NOTHING;
"""

assign_scope_query = """
                            INSERT INTO scope_app (scope_id, app_id)
                            SELECT scope_id, $1
                            FROM scopes
                            WHERE scope_url = $2
                            ON CONFLICT (scope_id, app_id) DO NOTHING; """

update_redirect_uri_query = """
UPDATE app_integration.app_info
SET redirect_uri = $1,
    updated_at   = now()
WHERE app_code = $2
RETURNING app_code;
"""

get_order_statuses_query = """
SELECT order_id, local_status, tracking_number, carrier_code, shipped_at
FROM app_integration.ebay_order_status
WHERE app_code = $1
  AND order_id = ANY($2::TEXT[])
"""

upsert_order_status_query = """
INSERT INTO app_integration.ebay_order_status
    (order_id, app_code, local_status, tracking_number, carrier_code, shipped_at, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, now())
ON CONFLICT (order_id, app_code) DO UPDATE SET
    local_status    = EXCLUDED.local_status,
    tracking_number = COALESCE(EXCLUDED.tracking_number,
                               app_integration.ebay_order_status.tracking_number),
    carrier_code    = COALESCE(EXCLUDED.carrier_code,
                               app_integration.ebay_order_status.carrier_code),
    shipped_at      = COALESCE(EXCLUDED.shipped_at,
                               app_integration.ebay_order_status.shipped_at),
    updated_at      = now()
"""
