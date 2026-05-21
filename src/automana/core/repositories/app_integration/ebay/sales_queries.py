"""SQL queries for EbaySalesRepository."""

ENSURE_PRODUCT = """
WITH new_product AS (
    INSERT INTO pricing.product_ref (game_id)
    SELECT 1
    WHERE NOT EXISTS (
        SELECT 1 FROM pricing.mtg_card_products WHERE card_version_id = $1
    )
    RETURNING product_id
),
link AS (
    INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
    SELECT product_id, $1 FROM new_product
    ON CONFLICT (card_version_id) DO NOTHING
)
SELECT product_id FROM pricing.mtg_card_products WHERE card_version_id = $1;
"""

UPSERT_LISTING_TEMPLATE = """
INSERT INTO app_integration.listing_template
    (app_code, product_id, condition_id, finish_id, language_id, marketplace_id,
     price_cents, quantity)
VALUES ($1, $2,
    (SELECT condition_id FROM pricing.card_condition     WHERE UPPER(code) = UPPER($3)),
    (SELECT finish_id    FROM card_catalog.card_finished WHERE UPPER(code) = UPPER($4)),
    (SELECT language_id  FROM card_catalog.language_ref  WHERE code = $5),
    $6, $7, $8)
ON CONFLICT (app_code, product_id, condition_id, finish_id, language_id, marketplace_id)
DO UPDATE SET
    price_cents = EXCLUDED.price_cents,
    quantity    = EXCLUDED.quantity,
    updated_at  = now()
RETURNING template_id;
"""

GET_LISTING_VARIANT = """
SELECT condition_id, finish_id, language_id, marketplace_id
FROM app_integration.ebay_active_listings
WHERE item_id = $1;
"""

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
    (item_id, app_code, card_version_id, product_id,
     condition_id, finish_id, language_id, marketplace_id, listed_at)
VALUES (
    $1, $2, $3,
    (SELECT product_id   FROM pricing.mtg_card_products      WHERE card_version_id = $3),
    (SELECT condition_id FROM pricing.card_condition          WHERE UPPER(code) = UPPER($4)),
    (SELECT finish_id    FROM card_catalog.card_finished      WHERE UPPER(code) = UPPER($5)),
    (SELECT language_id  FROM card_catalog.language_ref       WHERE code = $6),
    $7, $8
)
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
     language_id, sold_at, buyer_username, marketplace_id)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
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

UPSERT_PRICE_OBSERVATION = """
INSERT INTO pricing.price_observation
    (ts_date, source_product_id, price_type_id, finish_id, condition_id,
     language_id, data_provider_id, sold_avg_cents, sold_count)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)
DO UPDATE SET
    sold_avg_cents = EXCLUDED.sold_avg_cents,
    sold_count     = EXCLUDED.sold_count,
    updated_at     = now();
"""

GET_LISTING_META_BATCH = """
SELECT
    eal.item_id,
    eal.card_version_id,
    cf.code  AS finish_code,
    cc.code  AS condition_code
FROM app_integration.ebay_active_listings eal
JOIN card_catalog.card_finished   cf ON cf.finish_id    = COALESCE(eal.finish_id,    pricing.default_finish_id())
JOIN pricing.card_condition       cc ON cc.condition_id = COALESCE(eal.condition_id, pricing.default_condition_id())
WHERE eal.item_id  = ANY($1::TEXT[])
  AND eal.app_code = $2
  AND eal.card_version_id IS NOT NULL
"""

GET_LISTING_META = """
SELECT
    eal.card_version_id,
    COALESCE(eal.finish_id,    pricing.default_finish_id())    AS finish_id,
    COALESCE(eal.condition_id, pricing.default_condition_id()) AS condition_id,
    COALESCE(eal.language_id,  card_catalog.default_language_id()) AS language_id,
    cf.code  AS finish_code,
    cc.code  AS condition_code
FROM app_integration.ebay_active_listings eal
JOIN card_catalog.card_finished   cf ON cf.finish_id    = COALESCE(eal.finish_id,    pricing.default_finish_id())
JOIN pricing.card_condition       cc ON cc.condition_id = COALESCE(eal.condition_id, pricing.default_condition_id())
WHERE eal.item_id  = $1
  AND eal.app_code = $2
"""

GET_LOCAL_SALES_PAGINATED = """
SELECT
    osp.order_id,
    eos.local_status,
    MAX(osp.buyer_username)        AS buyer_username,
    MAX(osp.sold_at)               AS sold_at,
    MAX(osp.currency)              AS currency,
    SUM(osp.sold_price_cents)::INT AS total_price_cents,
    json_agg(json_build_object(
        'legacyItemId', osp.item_id,
        'title',        osp.title,
        'quantity',     osp.quantity
    ) ORDER BY osp.ebay_osp_id)    AS line_items
FROM app_integration.ebay_order_source_product osp
JOIN app_integration.ebay_order_status eos
    ON eos.order_id = osp.order_id AND eos.app_code = osp.app_code
WHERE osp.app_code = $1
GROUP BY osp.order_id, eos.local_status
ORDER BY MAX(osp.sold_at) DESC
LIMIT $2 OFFSET $3;
"""

COUNT_LOCAL_SALES = """
SELECT COUNT(DISTINCT order_id) AS total
FROM app_integration.ebay_order_source_product
WHERE app_code = $1;
"""
