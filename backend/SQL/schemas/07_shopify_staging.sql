CREATE UNLOGGED TABLE shopify_staging_raw (
    product_id BIGINT,
    date DATE,
    variation VARCHAR,
    price NUMERIC,
    scraped_at TIMESTAMP,
    card_id BIGINT,
    tcg_id BIGINT
);

CREATE OR REPLACE FUNCTION find_card_version(title)

CREATE INDEX idx_shopify_staging_raw_product_id ON shopify_staging_raw(product_id);
CREATE INDEX idx_shopify_staging_raw_date ON shopify_staging_raw(date);     

CREATE OR REPLACE PROCEDURE raw_to_dim()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Insert into the dimension table from the staging table
    INSERT INTO shopify_dim (product_id, date, variation, price, scraped_at)
    SELECT product_id, date, variation, price, scraped_at
    FROM shopify_staging_raw;

    -- Optionally, you can add logic to handle updates or deletions
END;
$$