BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS app_integration;
--TABLES---------------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS app_integration.app_info(
    --needs to be updated, maybe add cient id??
    app_id TEXT PRIMARY KEY,
    app_name VARCHAR(100) NOT NULL,
    redirect_uri VARCHAR(255) NOT NULL,
    response_type VARCHAR(20) NOT NULL,
    client_secret_encrypted TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'SANDBOX',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE,
    app_code VARCHAR(50) UNIQUE NOT NULL,
    UNIQUE (app_id, environment)
);


CREATE TABLE IF NOT EXISTS app_integration.app_user (
    user_id UUID REFERENCES user_management.users(unique_id) ON DELETE CASCADE NOT NULL,
    app_id TEXT REFERENCES app_integration.app_info(app_id )  ON DELETE CASCADE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (user_id, app_id)
);

CREATE TABLE IF NOT EXISTS app_integration.ebay_tokens(
    token_id SERIAL PRIMARY KEY,
    app_id TEXT REFERENCES app_integration.app_info(app_id) ON DELETE CASCADE NOT NULL,
    token TEXT NOT NULL,
    acquired_on TIMESTAMPTZ DEFAULT now(),
    expires_on TIMESTAMPTZ NOT NULL,
    token_type TEXT,
    used BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS app_integration.scopes (
    scope_id SERIAL PRIMARY KEY, 
    scope_url TEXT UNIQUE NOT NULL, 
    scope_description TEXT 
);
--new implementation -> allowed to an app, and then user with a subset of that
CREATE TABLE IF NOT EXISTS app_integration.scope_app (
    scope_id INT REFERENCES app_integration.scopes(scope_id) ON DELETE CASCADE, 
    app_id TEXT REFERENCES app_integration.app_info(app_id), 
    granted_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (scope_id, app_id)
);

CREATE TABLE IF NOT EXISTS app_integration.scopes_user(
    scope_id INT REFERENCES app_integration.scopes(scope_id) ON DELETE CASCADE,
    user_id UUID REFERENCES user_management.users(unique_id) ON DELETE CASCADE,
    app_id TEXT REFERENCES app_integration.app_info(app_id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (scope_id, user_id)
);

CREATE TABLE IF NOT EXISTS app_integration.log_oauth_request (
    unique_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES user_management.users(unique_id) ON DELETE CASCADE,
    app_id TEXT REFERENCES app_integration.app_info(app_id) ON DELETE CASCADE,
    request TEXT,
    timestamp TIMESTAMPTZ DEFAULT now(),
    expires_on TIMESTAMPTZ DEFAULT now() + INTERVAL '1 minute',
    status TEXT NOT NULL
);
-- Previously: `CREATE INDEX idx_oauth_session ON log_oauth_request(session_id);`
-- That column does not exist on this table; the index is dropped. If a
-- user→request lookup is needed, index on user_id instead:
CREATE INDEX IF NOT EXISTS idx_oauth_user ON app_integration.log_oauth_request(user_id);
COMMIT;
-- SEED DATA -----------------------------------------------------------------------------------------------------------------------------------------
-- eBay OAuth scopes — sourced from official OAS3 specs (github.com/hendt/ebay-api/specs/).
-- Idempotent on rebuilds. Only request scopes that are granted to your app in the eBay Developer Portal.
INSERT INTO app_integration.scopes (scope_url, scope_description) VALUES
    -- Public / baseline (client-credentials grant)
    ('https://api.ebay.com/oauth/api_scope',                                        'View public data from eBay'),
    -- Sell — inventory
    ('https://api.ebay.com/oauth/api_scope/sell.inventory',                         'View and manage your inventory and offers'),
    ('https://api.ebay.com/oauth/api_scope/sell.inventory.readonly',                'View your inventory and offers'),
    -- Sell — account
    ('https://api.ebay.com/oauth/api_scope/sell.account',                           'View and manage your account settings'),
    ('https://api.ebay.com/oauth/api_scope/sell.account.readonly',                  'View your account settings'),
    -- Sell — fulfillment / orders
    ('https://api.ebay.com/oauth/api_scope/sell.fulfillment',                       'View and manage your order fulfillments'),
    ('https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly',              'View your order fulfillments'),
    -- Sell — finances / payouts
    ('https://api.ebay.com/oauth/api_scope/sell.finances',                          'View and manage your payment and order information'),
    -- Sell — marketing / promotions
    ('https://api.ebay.com/oauth/api_scope/sell.marketing',                         'View and manage your eBay marketing activities, such as ad campaigns and listing promotions'),
    ('https://api.ebay.com/oauth/api_scope/sell.marketing.readonly',                'View your eBay marketing activities, such as ad campaigns and listing promotions'),
    -- Sell — analytics
    ('https://api.ebay.com/oauth/api_scope/sell.analytics.readonly',                'View your selling analytics data, such as performance reports'),
    -- Sell — marketplace insights
    ('https://api.ebay.com/oauth/api_scope/sell.marketplace.insights.readonly',     'View product selling data to help make pricing and stocking decisions'),
    -- Sell — compliance
    ('https://api.ebay.com/oauth/api_scope/sell.item.draft',                        'View and manage your item drafts'),
    -- Sell — logistics (Limited Release — must be requested from eBay)
    ('https://api.ebay.com/oauth/api_scope/sell.logistics',                         'Access Logistics information for shipments and shipping labels'),
    -- Sell — negotiation
    ('https://api.ebay.com/oauth/api_scope/sell.payment.dispute',                   'View and manage disputes and related payment and order information'),
    -- Sell — metadata
    ('https://api.ebay.com/oauth/api_scope/metadata.insights',                      'View metadata insights such as aspect relevance'),
    -- Buy — orders
    ('https://api.ebay.com/oauth/api_scope/buy.order',                              'View and manage your purchases'),
    ('https://api.ebay.com/oauth/api_scope/buy.order.readonly',                     'View your order details'),
    ('https://api.ebay.com/oauth/api_scope/buy.guest.order',                        'Purchase eBay items off eBay without signing in'),
    -- Buy — browse / feeds
    ('https://api.ebay.com/oauth/api_scope/buy.item.feed',                          'View curated feeds of eBay items'),
    ('https://api.ebay.com/oauth/api_scope/buy.item.bulk',                          'Retrieve eBay items in bulk'),
    ('https://api.ebay.com/oauth/api_scope/buy.product.feed',                       'Access curated feeds of eBay catalog products'),
    -- Buy — marketing / deals
    ('https://api.ebay.com/oauth/api_scope/buy.marketing',                          'Retrieve eBay product and listing data for marketing purposes'),
    ('https://api.ebay.com/oauth/api_scope/buy.deal',                               'View eBay sale events and deals'),
    -- Buy — marketplace insights
    ('https://api.ebay.com/oauth/api_scope/buy.marketplace.insights',               'View historical sales data to help buyers make informed purchasing decisions'),
    -- Buy — shopping cart
    ('https://api.ebay.com/oauth/api_scope/buy.shopping.cart',                      'View and manage your eBay shopping cart'),
    -- Commerce — catalog
    ('https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly',              'Search and view eBay catalog product information'),
    -- Commerce — identity
    ('https://api.ebay.com/oauth/api_scope/commerce.identity.readonly',             'View a user''s basic information such as username or business account details'),
    ('https://api.ebay.com/oauth/api_scope/commerce.identity.email.readonly',       'View a user''s personal email from their eBay member account'),
    ('https://api.ebay.com/oauth/api_scope/commerce.identity.phone.readonly',       'View a user''s personal telephone from their eBay member account'),
    ('https://api.ebay.com/oauth/api_scope/commerce.identity.address.readonly',     'View a user''s address from their eBay member account'),
    ('https://api.ebay.com/oauth/api_scope/commerce.identity.name.readonly',        'View a user''s first and last name from their eBay member account'),
    -- Commerce — notifications
    ('https://api.ebay.com/oauth/api_scope/commerce.notification.subscription',     'View and manage your event notification subscriptions'),
    ('https://api.ebay.com/oauth/api_scope/commerce.notification.subscription.readonly', 'View your event notification subscriptions')
ON CONFLICT (scope_url) DO NOTHING;

-- VIEWS -----------------------------------------------------------------------------------------------------------------------------------------------

--FUNCTIONS----------------------------------------------------------------------------------------------------------------------------------------------
