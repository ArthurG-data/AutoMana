-- migration_24_prod_scopes_sync.sql
--
-- Syncs scope_app for automana-production-v1 to exactly match the eBay Developer
-- Portal's approved scope list (Authorization Code + Client Credential grant types).
--
-- All 20 existing scope_app rows are correct; this adds the 6 missing ones.
-- Note: sell.edelivery uses /oauth/scope/ (not /oauth/api_scope/) — eBay's own URL.

BEGIN;

-- 1. Ensure all portal-approved scopes exist in the scopes catalogue.
INSERT INTO app_integration.scopes (scope_url, scope_description) VALUES
    ('https://api.ebay.com/oauth/api_scope/sell.finances',
     'View and manage your payment and order information to display this information to you and allow you to initiate refunds using the third party application'),
    ('https://api.ebay.com/oauth/api_scope/sell.reputation.readonly',
     'View your reputation data, such as feedback'),
    ('https://api.ebay.com/oauth/scope/sell.edelivery',
     'Allows access to eDelivery International Shipping APIs'),
    ('https://api.ebay.com/oauth/api_scope/commerce.vero',
     'Allows access to APIs that are related to eBay''s Verified Rights Owner (VeRO) program'),
    ('https://api.ebay.com/oauth/api_scope/commerce.shipping',
     'View and manage shipping information'),
    ('https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly',
     'Allows readonly access to Feedback APIs')
ON CONFLICT (scope_url) DO NOTHING;

-- 2. Link the missing scopes to the production app.
INSERT INTO app_integration.scope_app (scope_id, app_id)
SELECT s.scope_id, ai.app_id
FROM app_integration.scopes s
CROSS JOIN app_integration.app_info ai
WHERE ai.app_code = 'automana-production-v1'
  AND s.scope_url IN (
    'https://api.ebay.com/oauth/api_scope/sell.finances',
    'https://api.ebay.com/oauth/api_scope/sell.reputation.readonly',
    'https://api.ebay.com/oauth/scope/sell.edelivery',
    'https://api.ebay.com/oauth/api_scope/commerce.vero',
    'https://api.ebay.com/oauth/api_scope/commerce.shipping',
    'https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly'
  )
ON CONFLICT DO NOTHING;

COMMIT;
