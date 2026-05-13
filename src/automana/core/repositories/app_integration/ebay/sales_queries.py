"""SQL queries for EbaySalesRepository."""

ENSURE_SOURCE_PRODUCT = """
WITH ins AS (
    INSERT INTO pricing.source_product (product_id, source_id)
    SELECT mcp.product_id, $2
    FROM pricing.mtg_card_products mcp
    WHERE mcp.card_version_id = $1
    ON CONFLICT (product_id, source_id) DO NOTHING
    RETURNING source_product_id
)
SELECT source_product_id FROM ins
UNION ALL
SELECT sp.source_product_id
FROM pricing.source_product sp
JOIN pricing.mtg_card_products mcp ON mcp.product_id = sp.product_id
WHERE mcp.card_version_id = $1 AND sp.source_id = $2
LIMIT 1;
"""

UPSERT_ACTIVE_LISTING = """
INSERT INTO app_integration.ebay_active_listings
    (item_id, app_code, card_version_id, listed_at)
VALUES ($1, $2, $3, $4)
ON CONFLICT (item_id) DO UPDATE SET ended_at = NULL;
"""

GET_CARD_VERSION_BY_ITEM = """
SELECT card_version_id
FROM app_integration.ebay_active_listings
WHERE item_id = $1;
"""

GET_LISTED_CARD_VERSIONS = """
SELECT DISTINCT card_version_id
FROM app_integration.ebay_active_listings
WHERE app_code = $1;
"""

UPSERT_ORDER_SOURCE_PRODUCT = """
INSERT INTO app_integration.ebay_order_source_product
    (order_id, app_code, item_id, title, source_product_id,
     quantity, sold_price_cents, currency, finish_id, condition_id,
     language_id, sold_at, buyer_username)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
ON CONFLICT (order_id, app_code, item_id) DO UPDATE SET
    source_product_id = EXCLUDED.source_product_id,
    sold_price_cents   = EXCLUDED.sold_price_cents,
    updated_at         = now();
"""

GET_UNPROMOTED_OWN_SALES = """
SELECT ebay_osp_id, source_product_id, sold_price_cents, sold_at,
       finish_id, condition_id, language_id
FROM app_integration.ebay_order_source_product
WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;
"""

MARK_OWN_SALES_PROMOTED = """
UPDATE app_integration.ebay_order_source_product
SET promoted_to_obs = true
WHERE ebay_osp_id = ANY($1::bigint[]);
"""
