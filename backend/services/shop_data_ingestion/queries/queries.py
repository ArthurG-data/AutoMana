#insert a new price for a product in a shop

insert_market_query ="""
INSERT INTO markets_ref ( market_name, base_url, created_at , updated_at)
VALUES ($1, $2, now(), now())
ON CONFLICT (market_name) DO NOTHING"""

insert_collection_query = """
INSERT INTO collection_handles(collection_name, market_id, created_at, updated_at)
VALUES ($1, $2, now(), now())
ON CONFLICT (collection_name, market_id) DO NOTHING"""

insert_product_ref_query = """
INSERT INTO product_refs (product_shop_id, product_id, market_id, created_at, updated_at)
VALUES ($1, $2, now(), now())
ON CONFLICT (product_shop_id) DO NOTHING"""

insert_product_price_query = """
INSERT INTO product_prices (product_shop_id, price, time, source)
VALUES ($1, $2, $3, $4)"""

insert_products_ref = """
INSERT INTO card_product_refs (card_id, product_shop_id, description, quantity, created_at, upadted_at)
VALUES ($1, $2, $3, $4, $5, now())
ON CONFLICT (card_id, product_shop_id) DO NOTHING
"""
