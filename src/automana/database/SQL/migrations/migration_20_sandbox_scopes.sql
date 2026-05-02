-- Adds scopes present in the eBay sandbox app (Authorization Code Grant +
-- Client Credential Grant) that were not included in the initial seed.
-- Idempotent: ON CONFLICT DO NOTHING.

INSERT INTO app_integration.scopes (scope_url, scope_description) VALUES
    -- Buy — auctions
    ('https://api.ebay.com/oauth/api_scope/buy.offer.auction',             'View and manage bidding activities for auctions'),
    -- Buy — guest order proxy (Client Credential Grant)
    ('https://api.ebay.com/oauth/api_scope/buy.proxy.guest.order',         'Purchase eBay items anywhere, using an external vault for PCI compliance'),
    -- Commerce — identity status
    ('https://api.ebay.com/oauth/api_scope/commerce.identity.status.readonly', 'View a user''s eBay member account status'),
    -- Commerce — feedback
    ('https://api.ebay.com/oauth/api_scope/commerce.feedback',             'Allows access to Feedback APIs'),
    ('https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly',    'Allows readonly access to Feedback APIs'),
    -- Commerce — messaging
    ('https://api.ebay.com/oauth/api_scope/commerce.message',              'Allows access to eBay Message APIs'),
    -- Commerce — shipping
    ('https://api.ebay.com/oauth/api_scope/commerce.shipping',             'View and manage shipping information'),
    -- Commerce — VeRO
    ('https://api.ebay.com/oauth/api_scope/commerce.vero',                 'Allows access to APIs related to eBay''s Verified Rights Owner (VeRO) program'),
    -- Sell — item
    ('https://api.ebay.com/oauth/api_scope/sell.item',                     'View and manage your item information'),
    -- Sell — inventory mapping
    ('https://api.ebay.com/oauth/api_scope/sell.inventory.mapping',        'Manage and enhance inventory listings through the Inventory Mapping API'),
    -- Sell — reputation
    ('https://api.ebay.com/oauth/api_scope/sell.reputation',               'View and manage your reputation data, such as feedback'),
    ('https://api.ebay.com/oauth/api_scope/sell.reputation.readonly',      'View your reputation data, such as feedback'),
    -- Sell — stores
    ('https://api.ebay.com/oauth/api_scope/sell.stores',                   'View and manage eBay stores'),
    ('https://api.ebay.com/oauth/api_scope/sell.stores.readonly',          'View eBay stores')
ON CONFLICT (scope_url) DO NOTHING;
