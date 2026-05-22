"""SQL queries for EbayScrapeSoldRepository."""

INSERT_SCRAPED_SOLD = """
INSERT INTO pricing.ebay_scraped_sold
    (item_id, title, source_product_id, price_cents, currency, marketplace_id,
     condition_id, finish_id, language_id, sold_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (item_id) DO NOTHING;
"""

GET_UNPROMOTED_SCRAPED = """
SELECT scrape_id, source_product_id, price_cents, sold_at,
       finish_id, condition_id, language_id
FROM pricing.ebay_scraped_sold
WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;
"""

MARK_SCRAPED_PROMOTED = """
UPDATE pricing.ebay_scraped_sold
SET promoted_to_obs = true
WHERE scrape_id = ANY($1::bigint[]);
"""

GET_SCRAPE_TARGETS = """
SELECT card_version_id
FROM pricing.ebay_scrape_targets
WHERE is_active = true
ORDER BY last_scraped_at NULLS FIRST;
"""

REFRESH_SCRAPE_TARGETS = """
INSERT INTO pricing.ebay_scrape_targets (card_version_id, added_by)
SELECT DISTINCT cv.card_version_id, 'auto'
FROM card_catalog.v_card_versions_complete cv
JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
JOIN pricing.source_product sp ON sp.product_id = mcp.product_id
JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
WHERE (cv.rarity_name IN ('mythic', 'rare', 'special') OR cv.is_promo = true)
  AND po.sell_avg_cents >= $1
  AND po.ts_date >= now() - interval '7 days'
ON CONFLICT (card_version_id) DO UPDATE SET is_active = true;
"""

UPDATE_TARGET_LAST_SCRAPED = """
UPDATE pricing.ebay_scrape_targets
SET last_scraped_at = now()
WHERE card_version_id = $1;
"""
