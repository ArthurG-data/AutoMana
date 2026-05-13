"""SQL queries for EbayScrapeSoldRepository."""

INSERT_SCRAPED_SOLD = """
INSERT INTO pricing.ebay_scraped_sold
    (item_id, title, source_product_id, price_cents, currency,
     condition_id, finish_id, language_id, sold_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
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
